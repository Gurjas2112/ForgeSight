"""
Custom transformer for the steel-defect pipeline — defined in an IMPORTABLE backend module so
the joblib-pickled `defect_pipeline_v1.joblib` unpickles at serve time (train and serve both
import this exact class). PCA-reconstruction-residual + kNN-distance-to-normal, fit on the
NEGATIVE (normal) rows inside fit() so cross-validation refits it per fold (leakage-safe).
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


class AnomalyFeatures(BaseEstimator, TransformerMixin):
    def __init__(self, n_components: int = 5, n_neighbors: int = 5):
        self.n_components = n_components
        self.n_neighbors = n_neighbors

    def fit(self, X, y=None):
        Xn = np.asarray(X, dtype=float)
        self.scaler_ = StandardScaler().fit(Xn)
        Xs = self.scaler_.transform(Xn)
        normal = Xs if y is None else Xs[np.asarray(y) == 0]
        if len(normal) < self.n_neighbors + 1:
            normal = Xs
        self.pca_ = PCA(n_components=min(self.n_components, Xs.shape[1])).fit(normal)
        self.knn_ = NearestNeighbors(n_neighbors=self.n_neighbors).fit(normal)
        return self

    def transform(self, X):
        Xs = self.scaler_.transform(np.asarray(X, dtype=float))
        recon = self.pca_.inverse_transform(self.pca_.transform(Xs))
        resid = np.linalg.norm(Xs - recon, axis=1, keepdims=True)
        kdist = self.knn_.kneighbors(Xs)[0].mean(axis=1, keepdims=True)
        return np.hstack([Xs, resid, kdist])
