"""
Rasch modeli (dixotomik, JMLE) — Milliy sertifikat uslubidagi baholash.

Model:  P(x=1) = 1 / (1 + exp(-(theta - b)))
  theta — o'quvchi qobiliyati (logit), b — savol qiyinligi (logit)

Bosqichlar:
 1. Hamma to'g'ri / hamma xato savollar va 0 yoki 100% olgan o'quvchilar
    kalibrovkadan chiqariladi (ular haqida ma'lumot yo'q).
 2. Savol qiyinliklari JMLE (Newton-Raphson) bilan topiladi, o'rtacha qiyinlik = 0.
 3. JMLE siljishi uchun (k-1)/k tuzatish beriladi.
 4. Har bir o'quvchining theta'si topiladi. 0 yoki 100% olganlar uchun
    standart 0.3 tuzatish ishlatiladi.
 5. theta -> ball (0..75) chiziqli o'tkazilib, daraja belgilanadi.

MUHIM: DTM ning theta -> ball o'tkazish formulasi ommaga e'lon qilinmagan.
Bu yerda ochiq va sozlanadigan chiziqli shkala ishlatilgan (LOGIT_RANGE).
"""
import numpy as np

MAX_BALL = 75.0        # Milliy sertifikat maksimal bali
LOGIT_RANGE = 3.0      # theta = -3..+3 logit  ->  0..75 ball
EXTREME_CORR = 0.3     # 0 yoki to'liq ball uchun standart tuzatish


def level(ball: float) -> str:
    """Milliy sertifikat darajalari (ball 1 xonagacha yaxlitlanadi)."""
    b = round(float(ball), 1)
    if b > 70:
        return "A+"
    if b >= 65:
        return "A"
    if b >= 60:
        return "B+"
    if b >= 55:
        return "B"
    if b >= 50:
        return "C+"
    if b >= 46:
        return "C"
    return "Sertifikat yo'q"


def theta_to_ball(theta):
    ball = MAX_BALL / 2 + (MAX_BALL / (2 * LOGIT_RANGE)) * np.asarray(theta, float)
    return np.clip(ball, 0.0, MAX_BALL)


def _prob(theta, b):
    return 1.0 / (1.0 + np.exp(-(theta[:, None] - b[None, :])))


def _solve_theta(r, b):
    """Berilgan b da (tuzatilgan) xom ball r ga mos theta ni topadi."""
    k = len(b)
    theta = np.log(r / (k - r))
    for _ in range(200):
        p = _prob(theta, b)
        w = (p * (1 - p)).sum(1)
        step = np.clip((r - p.sum(1)) / w, -1.0, 1.0)
        theta = theta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return theta


def fit(X):
    """
    X — (o'quvchilar x savollar) 0/1 matritsa.
    Natija: dict (person massivlari o'quvchilar tartibida, item — savollar tartibida).
    """
    X = np.asarray(X, float)
    n, k = X.shape

    # 1) ekstremal savol/o'quvchilarni takroran chiqarish
    item_ok = np.ones(k, bool)
    person_ok = np.ones(n, bool)
    while True:
        sub = X[person_ok][:, item_ok]
        ns, ks = sub.shape
        if ns < 2 or ks < 2:
            raise ValueError(
                "Rasch uchun yetarli ma'lumot yo'q: kamida 2 ta o'quvchi va 2 ta "
                "'aralash' (ba'zilari to'g'ri, ba'zilari xato) savol kerak."
            )
        isc, psc = sub.sum(0), sub.sum(1)
        new_i, new_p = item_ok.copy(), person_ok.copy()
        new_i[np.where(item_ok)[0][(isc == 0) | (isc == ns)]] = False
        new_p[np.where(person_ok)[0][(psc == 0) | (psc == ks)]] = False
        if (new_i == item_ok).all() and (new_p == person_ok).all():
            break
        item_ok, person_ok = new_i, new_p

    sub = X[person_ok][:, item_ok]
    ns, ks = sub.shape
    s_i, r_p = sub.sum(0), sub.sum(1)

    # 2) JMLE
    b = np.log((ns - s_i) / s_i)
    b -= b.mean()
    th = np.log(r_p / (ks - r_p))
    converged = False
    for _ in range(2000):
        p = _prob(th, b)
        w_p = (p * (1 - p)).sum(1)
        d_th = np.clip((r_p - p.sum(1)) / w_p, -1.0, 1.0)
        th = th + d_th
        p = _prob(th, b)
        w_i = (p * (1 - p)).sum(0)
        d_b = np.clip((p.sum(0) - s_i) / w_i, -1.0, 1.0)
        b = b + d_b
        b -= b.mean()
        if max(np.abs(d_th).max(), np.abs(d_b).max()) < 1e-7:
            converged = True
            break

    # 3) JMLE siljishini tuzatish
    b = b * (ks - 1) / ks
    b -= b.mean()

    # 4) barcha o'quvchilar uchun theta (kalibrovkaga kirgan savollar bo'yicha)
    r_all = X[:, item_ok].sum(1)
    r_adj = np.clip(r_all, EXTREME_CORR, ks - EXTREME_CORR)
    theta = _solve_theta(r_adj, b)
    p_all = _prob(theta, b)
    se = 1.0 / np.sqrt((p_all * (1 - p_all)).sum(1))

    # 5) ball, foiz, daraja
    ball = np.round(theta_to_ball(theta), 1)
    foiz = np.round(ball / MAX_BALL * 100, 1)
    daraja = [level(x) for x in ball]

    # savollar statistikasi (faqat kalibrovkadagi o'quvchilar bo'yicha)
    p_c = _prob(theta[person_ok], b)
    x_c = sub
    w_c = p_c * (1 - p_c)
    item_se = 1.0 / np.sqrt(w_c.sum(0))
    infit = ((x_c - p_c) ** 2).sum(0) / w_c.sum(0)
    outfit = (((x_c - p_c) ** 2) / w_c).mean(0)

    idx = np.where(item_ok)[0]
    items = []
    for j in range(k):
        correct = int(X[:, j].sum())
        row = {
            "index": j,
            "correct": correct,
            "pct": round(100.0 * correct / n, 1),
            "b": None, "se": None, "infit": None, "outfit": None,
            "status": "",
        }
        if item_ok[j]:
            m = int(np.where(idx == j)[0][0])
            row.update(b=float(b[m]), se=float(item_se[m]),
                       infit=float(infit[m]), outfit=float(outfit[m]),
                       status="Baholandi")
        else:
            row["status"] = ("Hamma to'g'ri — hisobga olinmadi" if correct == n
                             else "Hamma xato — hisobga olinmadi" if correct == 0
                             else "Hisobga olinmadi")
        items.append(row)

    # ishonchlilik (person separation reliability)
    reliability = None
    if person_ok.sum() >= 3:
        var_obs = np.var(theta[person_ok], ddof=1)
        mse = np.mean(se[person_ok] ** 2)
        if var_obs > 0:
            reliability = float(max(0.0, (var_obs - mse) / var_obs))

    return {
        "n_persons": n,
        "n_items": k,
        "n_items_used": int(item_ok.sum()),
        "n_persons_calibrated": int(person_ok.sum()),
        "raw_total": X.sum(1).astype(int),
        "raw_used": r_all.astype(int),
        "theta": theta,
        "se": se,
        "ball": ball,
        "foiz": foiz,
        "daraja": daraja,
        "items": items,
        "reliability": reliability,
        "converged": converged,
    }
