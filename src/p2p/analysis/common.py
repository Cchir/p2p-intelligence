"""Shared helpers: warehouse access and the point-in-time feature table used by every model."""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from p2p import config

SNAPSHOT = pd.Timestamp("2019-01-18 23:59:00")
CATEGORICALS = ["flow", "item_type", "document_type", "spend_area", "spend_class"]
NUMERICS = ["log_value", "doc_items", "has_requisition", "created_month", "created_weekday",
            "vendor_prior_items", "vendor_prior_days", "vendor_prior_rework"]


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.DB_PATH), read_only=read_only)


def query(sql: str) -> pd.DataFrame:
    with connect() as con:
        return con.execute(sql).df()


def write_table(name: str, df: pd.DataFrame) -> None:
    with connect(read_only=False) as con:
        con.execute("create schema if not exists analytics")
        con.register("_df", df)
        con.execute(f"create or replace table analytics.{name} as select * from _df")
        con.unregister("_df")


def item_features() -> pd.DataFrame:
    """One row per item, using only what was known when the item was created.

    Vendor history is computed with an as-of join: for each item, only earlier items of that vendor
    that had already finished count. Random-split vendor averages would leak the outcome.
    """
    df = query(
        """
        select i.item_id, i.document_id, i.vendor_id, i.flow, i.item_type, i.document_type, i.spend_area,
               i.spend_class, i.created_ts, i.first_clear_ts, i.deleted_ts, i.status, i.order_value_eur,
               i.days_create_to_clear, i.requisition_ts is not null and i.requisition_ts <= i.created_ts as has_requisition,
               i.n_rework_events, d.n_items as doc_items
        from fct_po_items i join fct_po_documents d using (document_id)
        where i.all_ts_valid
        order by i.item_id
        """
    )
    df["log_value"] = np.log1p(df["order_value_eur"].clip(lower=0))
    df["created_month"] = df["created_ts"].dt.month
    df["created_weekday"] = df["created_ts"].dt.weekday
    df["has_requisition"] = df["has_requisition"].astype(int)

    # Vendor history as of each item's creation.
    # Ties are common at minute resolution: stable sorts keep every run identical.
    done = df.dropna(subset=["first_clear_ts"]).sort_values(["first_clear_ts", "item_id"])
    done = done.assign(
        vendor_prior_items=done.groupby("vendor_id").cumcount() + 1,
        vendor_prior_days=done.groupby("vendor_id")["days_create_to_clear"].transform(
            lambda s: s.expanding().mean()),
        vendor_prior_rework=done.groupby("vendor_id")["n_rework_events"].transform(
            lambda s: (s > 0).astype(float).expanding().mean()),
    )[["vendor_id", "first_clear_ts", "vendor_prior_items", "vendor_prior_days", "vendor_prior_rework"]]
    df = pd.merge_asof(df.sort_values(["created_ts", "item_id"]), done, left_on="created_ts", right_on="first_clear_ts",
                       by="vendor_id", suffixes=("", "_h"), allow_exact_matches=False)
    df = df.drop(columns=["first_clear_ts_h"])
    df["vendor_prior_items"] = df["vendor_prior_items"].fillna(0)
    return df


def encode(df: pd.DataFrame, top: int = 12) -> pd.DataFrame:
    """Numeric features plus one-hot categoricals; rare levels are pooled into 'other'."""
    X = df[NUMERICS].astype(float).copy()
    for c in CATEGORICALS:
        keep = df[c].value_counts().head(top).index
        dummies = pd.get_dummies(df[c].where(df[c].isin(keep), "other"), prefix=c, dtype=float)
        X = pd.concat([X, dummies], axis=1)
    return X
