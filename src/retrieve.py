"""Hybrid retrieval: BM25 + a dense vector space, fused by reciprocal rank.

BM25 is implemented here rather than pulled in, so the runtime path keeps its
zero-dependency install. The dense arm uses TF-IDF + truncated SVD (LSA) from
scikit-learn, which is an eval-time dependency only.

BE PRECISE ABOUT THIS IN THE DECK: the dense arm is **LSA, not a neural
sentence embedding**. It captures term co-occurrence, not meaning. Calling it
"dense embeddings" without that qualifier would overstate it, and TrialGPT's
retrieval uses actual neural embeddings, so the two are not equivalent.
"""

import math
import re
from collections import Counter, defaultdict

TOKEN = re.compile(r"[a-z0-9]+")

STOP = set("""a an the and or of to in for with without on at by from as is are
was were be been being this that these those it its patient patients study
studies trial trials subject subjects participant participants must have has
had will not no any all other than more least prior within during following
who whom which he she his her they them their you your we our""".split())


def tokenize(text):
    return [t for t in TOKEN.findall((text or "").lower())
            if t not in STOP and len(t) > 1]


class BM25:
    """Okapi BM25. k1 and b at the usual defaults."""

    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = docs                       # list[list[str]]
        self.N = len(docs)
        self.len = [len(d) for d in docs]
        self.avgdl = sum(self.len) / max(self.N, 1)

        self.tf = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            df.update(set(d))
        # Robertson/Sparck-Jones idf, floored so a term in almost every
        # document cannot contribute a negative score.
        self.idf = {t: max(1e-6, math.log(1 + (self.N - n + 0.5) / (n + 0.5)))
                    for t, n in df.items()}
        self.postings = defaultdict(list)
        for i, tfi in enumerate(self.tf):
            for t in tfi:
                self.postings[t].append(i)

    def scores(self, query):
        q = tokenize(query) if isinstance(query, str) else query
        out = [0.0] * self.N
        for t in set(q):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.postings[t]:
                f = self.tf[i][t]
                denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avgdl)
                out[i] += idf * f * (self.k1 + 1) / denom
        return out


class DenseLSA:
    """TF-IDF projected by truncated SVD, compared with cosine.

    A dense vector space over term co-occurrence -- NOT a neural embedding.
    """

    def __init__(self, texts, dims=256, seed=0):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize

        self.vec = TfidfVectorizer(stop_words="english", min_df=2,
                                   max_features=60000, sublinear_tf=True)
        X = self.vec.fit_transform(texts)
        dims = min(dims, max(2, min(X.shape) - 1))
        self.svd = TruncatedSVD(n_components=dims, random_state=seed)
        self.M = normalize(self.svd.fit_transform(X))
        self._normalize = normalize

    def scores(self, query):
        v = self._normalize(self.svd.transform(self.vec.transform([query])))
        return (self.M @ v[0]).tolist()


def rrf(rankings, k=60):
    """Reciprocal rank fusion. Rank-based, so the arms need no score calibration."""
    fused = defaultdict(float)
    for ranking in rankings:
        for rank, doc in enumerate(ranking, 1):
            fused[doc] += 1.0 / (k + rank)
    return sorted(fused, key=fused.get, reverse=True)


def order(scores):
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)


class Hybrid:
    """BM25 + LSA over one document set, fused by reciprocal rank."""

    def __init__(self, texts, dims=256, use_dense=True):
        self.texts = texts
        self.bm25 = BM25([tokenize(t) for t in texts])
        self.dense = None
        if use_dense and len(texts) > 8:
            try:
                self.dense = DenseLSA(texts, dims=dims)
            except Exception:                    # noqa: BLE001
                self.dense = None                # degrade to lexical only

    def search(self, query, top=None):
        lex = self.bm25.scores(query)
        rankings = [order(lex)]
        if self.dense is not None:
            rankings.append(order(self.dense.scores(query)))
        fused = rrf(rankings)
        return fused[:top] if top else fused, lex
