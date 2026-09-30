-- Запрос собирает витрину дневной выручки и ROMI по каналам для DataLens.
-- Имена таблиц демонстрационные. Боевую схему не публикую.
-- Выручка на дате закрытия сделки, не на дате клика.
-- Окно по каналу нужно, чтобы на дашборде видеть накопленную выручку, а не только день.

WITH leads AS (
    SELECT
        toDate(created_at) AS day,
        channel,
        count() AS leads
    FROM demo.leads
    GROUP BY day, channel
),
payments AS (
    SELECT
        toDate(closed_at) AS day,
        channel,
        countIf(status = 'paid') AS payments,
        sumIf(amount, status = 'paid') AS revenue
    FROM demo.payments
    GROUP BY day, channel
),
spend AS (
    SELECT
        toDate(day) AS day,
        channel,
        sum(cost) AS ad_spend
    FROM demo.ad_spend
    GROUP BY day, channel
),
keys AS (
    SELECT day, channel FROM leads
    UNION DISTINCT
    SELECT day, channel FROM payments
    UNION DISTINCT
    SELECT day, channel FROM spend
)
SELECT
    k.day,
    k.channel,
    ifNull(l.leads, 0) AS leads,
    ifNull(p.payments, 0) AS payments,
    ifNull(p.revenue, 0) AS revenue,
    ifNull(s.ad_spend, 0) AS ad_spend,
    if(ifNull(l.leads, 0) = 0, NULL, round(s.ad_spend / l.leads, 2)) AS cpl,
    if(ifNull(s.ad_spend, 0) = 0, NULL, round(p.revenue / s.ad_spend, 2)) AS romi,
    sum(ifNull(p.revenue, 0)) OVER (
        PARTITION BY k.channel
        ORDER BY k.day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS revenue_cum
FROM keys AS k
LEFT JOIN leads AS l
    ON l.day = k.day AND l.channel = k.channel
LEFT JOIN payments AS p
    ON p.day = k.day AND p.channel = k.channel
LEFT JOIN spend AS s
    ON s.day = k.day AND s.channel = k.channel
ORDER BY k.day, k.channel
