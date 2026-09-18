"""
Rasch modeli (1PL IRT) — Joint Maximum Likelihood Estimation (JMLE).

Kirish: 0/1 matritsa (o'quvchilar x savollar).
Chiqish: theta (har bir o'quvchi qobiliyati) va beta (har bir savol qiyinligi),
ikkalasi ham logit shkalasida.

Eslatma: bu — soddalashtirilgan, mustaqil JMLE implementatsiyasi. Rasmiy milliy
sertifikat hisob-kitobi ankor (langar) savollar orqali bir nechta variantlarni
umumiy shkalaga tenglashtiradi; bu yerda esa faqat bitta test doirasidagi
natijalar nisbiy baholanadi (guruh ichida solishtirish uchun yetarli, lekin
rasmiy sertifikat metodikasining aniq nusxasi emas).
"""

import numpy as np


def estimate_rasch(matrix: np.ndarray, max_iter: int = 200, tol: float = 1e-4):
    matrix = np.asarray(matrix, dtype=float)
    n_persons, n_items = matrix.shape
    mask = ~np.isnan(matrix)

    scores_p = np.nansum(matrix, axis=1)
    scores_i = np.nansum(matrix, axis=0)
    n_p = mask.sum(axis=1)
    n_i = mask.sum(axis=0)

    def adjust(s, n):
        s = np.where(s <= 0, 0.3, s)
        s = np.where(s >= n, n - 0.3, s)
        return s

    sp = adjust(scores_p.copy(), n_p)
    si = adjust(scores_i.copy(), n_i)

    theta = np.log(sp / (n_p - sp))
    beta = -np.log(si / (n_i - si))
    beta -= beta.mean()

    for _ in range(max_iter):
        diff_theta = np.zeros(n_persons)
        for p in range(n_persons):
            items = mask[p]
            if not items.any():
                continue
            prob = 1 / (1 + np.exp(-(theta[p] - beta[items])))
            expected = prob.sum()
            info = (prob * (1 - prob)).sum()
            if info > 1e-6:
                diff_theta[p] = (scores_p[p] - expected) / info
        theta = theta + np.clip(diff_theta, -1, 1)

        diff_beta = np.zeros(n_items)
        for i in range(n_items):
            persons = mask[:, i]
            if not persons.any():
                continue
            prob = 1 / (1 + np.exp(-(theta[persons] - beta[i])))
            expected = prob.sum()
            info = (prob * (1 - prob)).sum()
            if info > 1e-6:
                diff_beta[i] = -(scores_i[i] - expected) / info
        beta = beta + np.clip(diff_beta, -1, 1)
        beta -= beta.mean()

        if np.max(np.abs(diff_theta)) < tol and np.max(np.abs(diff_beta)) < tol:
            break

    return theta, beta


def theta_to_percent(theta: np.ndarray) -> np.ndarray:
    """Theta (logit) qiymatlarini guruh ichida 0-100% shkalasiga o'giradi."""
    t_min, t_max = theta.min(), theta.max()
    if t_max - t_min < 1e-6:
        return np.full_like(theta, 50.0)
    return (theta - t_min) / (t_max - t_min) * 100


def daraja_from_percent(percent: float) -> str:
    if percent >= 70:
        return "A+"
    if percent >= 60:
        return "A"
    if percent >= 50:
        return "B+"
    if percent >= 40:
        return "B"
    if percent >= 30:
        return "C+"
    if percent >= 20:
        return "C"
    return "—"
