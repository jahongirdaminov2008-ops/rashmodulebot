"""
rasch.py - Matematika Milliy sertifikat uchun baholash moduli.

Ishlash tartibi:
1. Rasch modeli (JMLE) har bir savolning qiyinligini (b, logit) aniqlaydi.
   Kam odam yechgan savol -> b katta (qiyin).
2. Har bir savolga og'irlik beriladi: eng oson savol = 1, eng qiyin = 1 + HARDNESS.
3. Ball = (o'quvchi yig'gan og'irlik / jami og'irlik) * 100.
   Demak bir xil sondagi to'g'ri javob bergan ikki o'quvchidan qiyin
   savollarni yechgani yuqori ball oladi.
4. Rasch qobiliyati (theta) ham hisoblanadi (faqat ma'lumot uchun).

Kerak: numpy, pandas, openpyxl
"""

import numpy as np
import pandas as pd

HARDNESS = 1.0  # 0 -> barcha savol teng; 1 -> eng qiyin savol 2x, 2 -> 3x

# Milliy sertifikat darajalari (ball chegarasi, daraja)
LEVELS = [
    (70.0, "A+"),
    (65.0, "A"),
    (60.0, "B+"),
    (55.0, "B"),
    (50.0, "C+"),
    (46.0, "C"),
]
NO_LEVEL = "Sertifikatsiz"


def _logit(p):
    return np.log(p / (1.0 - p))


def rasch_jmle(X, max_iter=200, tol=1e-6):
    """
    X: (N o'quvchi x K savol) 0/1 massiv.
    Qaytaradi: theta (N,), b (K,) - logitlarda, b o'rtachasi 0.
    Hamma to'g'ri / hamma xato holatlari 0.5 tuzatish bilan hal qilinadi.
    """
    X = np.asarray(X, dtype=float)
    N, K = X.shape

    # Boshlang'ich qiymatlar (0.5 tuzatish - ekstremal holatlar uchun)
    item_p = (X.sum(axis=0) + 0.5) / (N + 1.0)
    person_p = (X.sum(axis=1) + 0.5) / (K + 1.0)
    b = -_logit(item_p)
    b -= b.mean()
    theta = _logit(person_p)

    # Kalibrovka uchun ekstremal o'quvchi/savollarni chiqarib tashlaymiz
    rs = X.sum(axis=1)
    cs = X.sum(axis=0)
    p_ok = (rs > 0) & (rs < K)
    i_ok = (cs > 0) & (cs < N)
    if p_ok.sum() < 3 or i_ok.sum() < 3:
        # Ma'lumot juda kam - PROX natijasi bilan cheklanamiz
        return theta, b

    Xc = X[np.ix_(p_ok, i_ok)]
    Nc, Kc = Xc.shape
    th = theta[p_ok].copy()
    bb = b[i_ok].copy()

    for _ in range(max_iter):
        P = 1.0 / (1.0 + np.exp(-(th[:, None] - bb[None, :])))
        W = P * (1.0 - P)

        # Savol qiyinligi (Newton qadami)
        d_b = -(Xc.sum(axis=0) - P.sum(axis=0)) / np.maximum(W.sum(axis=0), 1e-9)
        d_b = np.clip(d_b, -1.0, 1.0)
        bb_new = bb + d_b
        bb_new -= bb_new.mean()

        # O'quvchi qobiliyati (Newton qadami)
        P = 1.0 / (1.0 + np.exp(-(th[:, None] - bb_new[None, :])))
        W = P * (1.0 - P)
        d_t = (Xc.sum(axis=1) - P.sum(axis=1)) / np.maximum(W.sum(axis=1), 1e-9)
        d_t = np.clip(d_t, -1.0, 1.0)
        th_new = th + d_t

        delta = max(np.abs(bb_new - bb).max(), np.abs(th_new - th).max())
        bb, th = bb_new, th_new
        if delta < tol:
            break

    # JMLE siljishini tuzatish (L-1)/L
    bb = bb * (Kc - 1.0) / Kc

    # Kalibrovkadan tashqarida qolgan savollar uchun qiyinlik
    b_full = b.copy()
    b_full[i_ok] = bb
    if (~i_ok).any():
        # to'g'ri yechganlar ulushi bo'yicha, chegaralangan
        b_full[~i_ok] = np.clip(b[~i_ok], bb.min() - 1.0, bb.max() + 1.0)

    # Hamma o'quvchining qobiliyatini yakuniy b bo'yicha hisoblaymiz
    theta_full = _estimate_theta(X, b_full)
    return theta_full, b_full


def _estimate_theta(X, b, max_iter=100):
    """Har bir o'quvchi uchun MLE (ekstremal holatlarda 0.5 tuzatish)."""
    N, K = X.shape
    raw = X.sum(axis=1)
    adj = np.clip(raw, 0.5, K - 0.5)  # 0 va K uchun tuzatish
    th = _logit((adj) / K)
    for _ in range(max_iter):
        P = 1.0 / (1.0 + np.exp(-(th[:, None] - b[None, :])))
        W = np.maximum((P * (1.0 - P)).sum(axis=1), 1e-9)
        step = np.clip((adj - P.sum(axis=1)) / W, -1.0, 1.0)
        th = th + step
        if np.abs(step).max() < 1e-8:
            break
    return th


def item_weights(b, hardness=HARDNESS):
    """Eng oson savol = 1, eng qiyin savol = 1 + hardness."""
    b = np.asarray(b, dtype=float)
    span = b.max() - b.min()
    if span < 1e-9:
        return np.ones_like(b)
    return 1.0 + hardness * (b - b.min()) / span


def level_of(ball):
    for cut, name in LEVELS:
        if ball >= cut:
            return name
    return NO_LEVEL


def grade(X, names=None, hardness=HARDNESS):
    """
    X: (N x K) 0/1 natijalar. Qaytaradi: (natija DataFrame, savollar DataFrame).
    """
    X = np.asarray(X, dtype=float)
    N, K = X.shape
    if names is None:
        names = [f"O'quvchi {i + 1}" for i in range(N)]

    theta, b = rasch_jmle(X)
    w = item_weights(b, hardness)

    raw = X.sum(axis=1)
    ball = (X @ w) / w.sum() * 100.0

    res = pd.DataFrame(
        {
            "Ism": names,
            "To'g'ri": raw.astype(int),
            "Foiz": np.round(raw / K * 100.0, 1),
            "Ball": np.round(ball, 1),
            "Daraja": [level_of(round(v, 1)) for v in ball],
            "Theta": np.round(theta, 2),
        }
    )
    res = res.sort_values("Ball", ascending=False).reset_index(drop=True)
    res.insert(0, "O'rin", np.arange(1, N + 1))

    items = pd.DataFrame(
        {
            "Savol": np.arange(1, K + 1),
            "Yechgan %": np.round(X.mean(axis=0) * 100.0, 1),
            "Qiyinlik (b)": np.round(b, 2),
            "Og'irlik": np.round(w, 2),
        }
    )
    return res, items


def grade_excel(path, hardness=HARDNESS):
    """
    Excel: birinchi ustun(lar) - ism (matn), qolganlari - savollar (1 yoki 0).
    """
    df = pd.read_excel(path)
    q_cols = []
    for c in df.columns:
        col = pd.to_numeric(df[c], errors="coerce")
        if col.notna().all() and set(col.unique()) <= {0, 1}:
            q_cols.append(c)
    if not q_cols:
        raise ValueError("Excelda 1/0 dan iborat savol ustunlari topilmadi.")

    name_cols = [c for c in df.columns if c not in q_cols]
    if name_cols:
        names = df[name_cols[0]].astype(str).tolist()
    else:
        names = None

    X = df[q_cols].apply(pd.to_numeric).to_numpy(dtype=float)
    return grade(X, names, hardness)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Foydalanish: python rasch.py natijalar.xlsx")
        raise SystemExit(1)
    result, items = grade_excel(sys.argv[1])
    print(result.to_string(index=False))
    print()
    print(items.to_string(index=False))
