SELECT p.label AS period, COUNT(*) AS total,
       SUM(CASE WHEN o.completed_at_utc <= o.promised_delivery_at_utc THEN 1 ELSE 0 END) AS on_time
FROM orders o
JOIN reporting_periods p ON o.promised_delivery_at_utc >= p.starts_at_utc
  AND o.promised_delivery_at_utc < p.ends_at_utc
JOIN shipments s ON s.order_id = o.order_id
WHERE o.order_status <> 'cancelled'
GROUP BY p.label ORDER BY p.label
