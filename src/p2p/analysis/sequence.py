"""Predictive process monitoring with a recurrent network (PyTorch).

After every event on an open item, predict the next activity and how long the item has left.
A two-headed GRU reads the event sequence so far. It is judged against the process-mining baselines
a team could build without deep learning: a second-order Markov chain for the next step and the
median remaining time by last activity and position. Split by time; test items have over five
months of follow-up.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from p2p.analysis.common import query

log = logging.getLogger(__name__)
MAX_LEN = 30
TRAIN_END, TEST_START, TEST_END = "2018-05-15", "2018-06-01", "2018-08-01"
TRAIN_CASES, TEST_CASES = 60_000, 20_000
USER_TYPES = {"human": 0, "batch": 1, "none": 2}


def load() -> pd.DataFrame:
    return query(
        f"""
        select e.item_id, e.event_no, e.activity, e.user_type, e.event_ts, i.created_ts, i.first_event_ts, i.last_event_ts
        from fct_item_events e join fct_po_items i using (item_id)
        where i.all_ts_valid and i.created_ts < date '{TEST_END}' and e.event_no <= {MAX_LEN}
        order by e.item_id, e.event_no
        """
    )


def make_arrays(df: pd.DataFrame, vocab: dict) -> list[dict]:
    eos = vocab["<end>"]
    out = []
    for item, g in df.groupby("item_id", sort=False):
        a = g["activity"].map(vocab).to_numpy(np.int64)
        ts = g["event_ts"].to_numpy("datetime64[s]").astype(np.int64) / 86400.0
        end = g["last_event_ts"].iloc[0].timestamp() / 86400.0
        out.append({
            "item_id": item, "act": a, "user": g["user_type"].map(USER_TYPES).to_numpy(np.int64),
            "dt": np.log1p(np.diff(ts, prepend=ts[0]).clip(min=0)), "elapsed": np.log1p((ts - ts[0]).clip(min=0)),
            "next": np.append(a[1:], eos), "rem": (end - ts).clip(min=0),
        })
    return out


class EventGRU(nn.Module):
    def __init__(self, n_activities: int, emb: int = 32, hidden: int = 128, layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.act = nn.Embedding(n_activities + 1, emb, padding_idx=n_activities)
        self.user = nn.Embedding(4, 4, padding_idx=3)
        self.gru = nn.GRU(emb + 4 + 2, hidden, layers, batch_first=True, dropout=dropout)
        self.next_head = nn.Linear(hidden, n_activities)
        self.time_head = nn.Sequential(nn.Linear(hidden, 64), nn.ReLU(), nn.Linear(64, 1))

    def forward(self, act, user, num, lengths):
        x = torch.cat([self.act(act), self.user(user), num], dim=-1)
        packed = pack_padded_sequence(x, lengths.cpu(), batch_first=True, enforce_sorted=False)
        h, _ = pad_packed_sequence(self.gru(packed)[0], batch_first=True, total_length=act.shape[1])
        return self.next_head(h), self.time_head(h).squeeze(-1)


def collate(batch: list[dict], pad: int):
    L = max(len(b["act"]) for b in batch)

    def stack(key, fill, dtype):
        arr = np.full((len(batch), L), fill, dtype=dtype)
        for i, b in enumerate(batch):
            arr[i, : len(b[key])] = b[key]
        return torch.from_numpy(arr)

    return {"act": stack("act", pad, np.int64), "user": stack("user", 3, np.int64),
            "num": torch.stack([stack("dt", 0, np.float32), stack("elapsed", 0, np.float32)], -1),
            "next": stack("next", -100, np.int64), "rem": stack("rem", 0, np.float32),
            "lengths": torch.tensor([len(b["act"]) for b in batch])}


def train(data: list[dict], n_act: int, epochs: int = 6, bs: int = 256, seed: int = 42) -> EventGRU:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    model = EventGRU(n_act)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 3e-3, total_steps=epochs * (len(data) // bs + 1))
    ce = nn.CrossEntropyLoss(ignore_index=-100)
    for ep in range(epochs):
        model.train()
        order = rng.permutation(len(data))
        total = 0.0
        for s in range(0, len(order), bs):
            b = collate([data[i] for i in order[s:s + bs]], n_act)
            nxt, rem = model(b["act"], b["user"], b["num"], b["lengths"])
            mask = b["next"] != -100
            loss = ce(nxt.reshape(-1, n_act), b["next"].reshape(-1)) + (
                (rem[mask] - torch.log1p(b["rem"][mask])).abs().mean())
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            total += loss.item() * len(b["lengths"])
        log.info("epoch %d loss %.4f", ep + 1, total / len(data))
    return model


@torch.no_grad()
def predict(model: EventGRU, data: list[dict], n_act: int, bs: int = 512) -> pd.DataFrame:
    model.eval()
    rows = []
    for s in range(0, len(data), bs):
        chunk = data[s:s + bs]
        b = collate(chunk, n_act)
        nxt, rem = model(b["act"], b["user"], b["num"], b["lengths"])
        probs = nxt.softmax(-1)
        top = probs.argmax(-1).numpy()
        top3 = probs.topk(3, -1).indices.numpy()
        rem = torch.expm1(rem).clamp(min=0).numpy()
        for i, c in enumerate(chunk):
            n = len(c["act"])
            true = c["next"][:n]
            rows.append(pd.DataFrame({
                "item_id": c["item_id"], "pos": np.arange(1, n + 1), "last": c["act"][:n], "next": true,
                "pred_next": top[i, :n], "in_top3": (top3[i, :n] == true[:, None]).any(1),
                "rem": c["rem"][:n], "pred_rem": rem[i, :n],
            }))
    return pd.concat(rows, ignore_index=True)


def markov_baselines(train_data: list[dict], preds: pd.DataFrame, test_data: list[dict]) -> pd.DataFrame:
    """Second-order Markov next step, backing off to first order; median remaining by (last, position)."""
    r = pd.DataFrame([
        {"prev": prev, "last": a, "next": n, "pos": min(p, 15), "rem": rem}
        for c in train_data
        for p, (prev, a, n, rem) in enumerate(zip(np.r_[-1, c["act"][:-1]], c["act"], c["next"], c["rem"], strict=True), 1)
    ])
    second = r.groupby(["prev", "last"])["next"].agg(lambda s: s.mode().iat[0])
    first = r.groupby("last")["next"].agg(lambda s: s.mode().iat[0])
    time_tbl = r.groupby(["last", "pos"])["rem"].median()
    time_any = r.groupby("last")["rem"].median()

    prev = np.concatenate([np.r_[-1, c["act"][:-1]] for c in test_data])
    d = preds.assign(prev=prev)
    d["base_next"] = pd.MultiIndex.from_arrays([d["prev"], d["last"]]).map(second)
    d["base_next"] = d["base_next"].fillna(d["last"].map(first))
    d["base_rem"] = pd.MultiIndex.from_arrays([d["last"], d["pos"].clip(upper=15)]).map(time_tbl)
    d["base_rem"] = d["base_rem"].fillna(d["last"].map(time_any)).fillna(r["rem"].median())
    return d


def run():
    df = load()
    activities = sorted(df["activity"].unique())
    vocab = {a: i for i, a in enumerate(activities)}
    vocab["<end>"] = len(vocab)
    n_act = len(vocab)
    names = {i: a for a, i in vocab.items()}

    starts = df.groupby("item_id", sort=False)["created_ts"].first()
    rng = np.random.default_rng(0)
    tr_ids = starts[starts < TRAIN_END].index.to_numpy()
    te_ids = starts[(starts >= TEST_START) & (starts < TEST_END)].index.to_numpy()
    tr_ids = rng.choice(tr_ids, min(TRAIN_CASES, len(tr_ids)), replace=False)
    te_ids = rng.choice(te_ids, min(TEST_CASES, len(te_ids)), replace=False)
    tr = make_arrays(df[df["item_id"].isin(tr_ids)], vocab)
    te = make_arrays(df[df["item_id"].isin(te_ids)], vocab)
    log.info("sequence data: %d train cases, %d test cases, %d activities", len(tr), len(te), n_act)

    model = train(tr, n_act)
    preds = markov_baselines(tr, predict(model, te, n_act), te)

    def score(d: pd.DataFrame) -> dict:
        return {"prefixes": len(d), "next_acc_gru": float((d["pred_next"] == d["next"]).mean()),
                "next_acc_markov": float((d["base_next"] == d["next"]).mean()),
                "next_top3_gru": float(d["in_top3"].mean()),
                "rem_mae_gru": float((d["pred_rem"] - d["rem"]).abs().mean()),
                "rem_mae_baseline": float((d["base_rem"] - d["rem"]).abs().mean())}

    overall = pd.DataFrame([{"scope": "all prefixes", **score(preds)}])
    by_pos = pd.DataFrame([{"scope": f"after event {k}", **score(preds[preds["pos"] == k])} for k in (1, 2, 3, 5, 8)])
    results = pd.concat([overall, by_pos], ignore_index=True)
    log.info("sequence results\n%s", results.T)
    return results, {"n_train_cases": len(tr), "n_test_cases": len(te), "activities": [names[i] for i in range(n_act)]}
