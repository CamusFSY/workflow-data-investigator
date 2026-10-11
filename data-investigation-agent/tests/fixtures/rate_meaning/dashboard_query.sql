SELECT period, completed, timely, cancelled, total
FROM rate_samples WHERE cohort = 'distinct' ORDER BY period
