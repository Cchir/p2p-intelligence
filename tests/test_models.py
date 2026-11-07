"""Model correctness on data with a known answer: each method must recover the truth."""

import numpy as np
import pandas as pd
import torch

from p2p.analysis import alerts, bayes, causal, conformal, sequence
from p2p.analysis.common import CATEGORICALS, NUMERICS


def synthetic_items(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERICS})
    for c in CATEGORICALS:
        df[c] = rng.choice(["a", "b"], n)
    df["document_id"] = np.arange(n) // 2
    return df, rng


def test_dml_removes_confounding_and_recovers_the_effect():
    df, rng = synthetic_items()
    confounder = df["log_value"].to_numpy()
    p = 1 / (1 + np.exp(-1.5 * confounder))
    df["any_change"] = (rng.random(len(df)) < p).astype(int)
    df["unpaid_days"] = 60 + 3.0 * df["any_change"] + 20 * confounder + rng.normal(scale=5, size=len(df))
    r = causal.dml(df, "any_change", n_splits=3)
    assert r["naive_diff_days"] > 15, "the setup must really be confounded"
    assert r["ci_low"] < 3.0 < r["ci_high"]
    assert abs(r["placebo_effect_days"]) < 1.0


def test_dml_finds_no_effect_when_there_is_none():
    df, rng = synthetic_items(seed=1)
    confounder = df["log_value"].to_numpy()
    df["any_change"] = (rng.random(len(df)) < 1 / (1 + np.exp(-confounder))).astype(int)
    df["unpaid_days"] = 60 + 20 * confounder + rng.normal(scale=5, size=len(df))
    r = causal.dml(df, "any_change", n_splits=3)
    assert r["ci_low"] < 0 < r["ci_high"]


def test_conformal_reaches_target_coverage_from_a_bad_interval():
    rng = np.random.default_rng(2)
    y = rng.normal(size=60_000)
    lo, hi = np.full_like(y, -0.5), np.full_like(y, 0.5)  # far too narrow for 90%
    q = conformal.cqr_correction(y[:20_000], lo[:20_000], hi[:20_000], alpha=0.1)
    covered = np.mean((y[20_000:] >= lo[20_000:] - q) & (y[20_000:] <= hi[20_000:] + q))
    assert 0.885 < covered < 0.915


def test_hierarchical_model_shrinks_small_vendors_but_not_large_ones():
    agg = pd.DataFrame({
        "vendor_id": [f"v{i}" for i in range(42)], "spend_area": ["x"] * 42,
        "n": [3, 1000] + [100] * 40,
        "y": [3, 500] + list(np.random.default_rng(3).binomial(100, 0.1, 40)),
    })
    mcmc, _, vendors = bayes.fit(agg, warmup=300, samples=300, chains=1)
    post = mcmc.get_samples()
    rates = bayes._predict_vendor_rate(post, vendors, np.zeros(2, int), np.array([vendors["v0"], vendors["v1"]])).mean(axis=0)
    assert rates[0] < 0.75, "3 of 3 must not be believed at face value"
    assert abs(rates[1] - 0.5) < 0.05, "1,000 items should speak for themselves"


def test_cost_curve_arithmetic():
    scored = pd.DataFrame({"p_correction": [0.9, 0.8, 0.1, 0.05], "corrected": [1, 1, 0, 0]})
    c = alerts.cost_curve(scored, review_cost_eur=10, correction_cost_eur=100, share_preventable=0.5)
    assert c["net_saving_eur"].tolist() == [40.0, 80.0, 70.0, 60.0]
    assert c.loc[c["net_saving_eur"].idxmax(), "reviewed"] == 2


def test_cost_curve_never_splits_tied_scores():
    scored = pd.DataFrame({"p_correction": [0.5, 0.5, 0.5, 0.1], "corrected": [0, 0, 1, 0]})
    c = alerts.cost_curve(scored, review_cost_eur=1, correction_cost_eur=10, share_preventable=1.0)
    assert c["reviewed"].tolist() == [3, 4]


def test_sequence_model_shapes_and_padding():
    pad = 5
    b = sequence.collate([
        {"act": np.array([0, 1, 2]), "user": np.array([0, 0, 1]), "dt": np.zeros(3, float), "elapsed": np.zeros(3, float),
         "next": np.array([1, 2, 4]), "rem": np.ones(3, float)},
        {"act": np.array([0]), "user": np.array([2]), "dt": np.zeros(1, float), "elapsed": np.zeros(1, float),
         "next": np.array([4]), "rem": np.zeros(1, float)},
    ], pad)
    assert b["act"][1, 1] == pad and b["next"][1, 2] == -100
    nxt, rem = sequence.EventGRU(pad)(b["act"], b["user"], b["num"], b["lengths"])
    assert nxt.shape == (2, 3, pad) and rem.shape == (2, 3)


def test_sequence_model_is_causal_in_time():
    """A prediction at step k must not change when later events change."""
    torch.manual_seed(0)
    m = sequence.EventGRU(5).eval()
    act = torch.tensor([[0, 1, 2, 3]])
    other = torch.tensor([[0, 1, 4, 4]])
    user, num = torch.zeros_like(act), torch.zeros(1, 4, 2)
    with torch.no_grad():
        a, _ = m(act, user, num, torch.tensor([4]))
        b, _ = m(other, user, num, torch.tensor([4]))
    assert torch.allclose(a[0, :2], b[0, :2])
    assert not torch.allclose(a[0, 2:], b[0, 2:])
