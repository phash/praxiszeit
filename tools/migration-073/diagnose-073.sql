-- diagnose-073.sql — rein lesend

-- Q1: Befund je Fenster und Wochentag
SELECT u.tenant_id, u.username, d.nr, d.tag, d.beginn, d.ende,
       CASE
         WHEN d.beginn IS NULL OR d.ende IS NULL           THEN 'halboffen'
         WHEN d.beginn >= d.ende                           THEN 'Beginn>=Ende'
         WHEN EXTRACT(SECOND FROM d.beginn) <> 0
           OR EXTRACT(SECOND FROM d.ende) <> 0             THEN 'Sekunden'
         ELSE 'ok'
       END AS befund
FROM users u
CROSS JOIN LATERAL (VALUES
  (1, 'Mo', u.scheduled_start_monday,    u.scheduled_end_monday),
  (2, 'Di', u.scheduled_start_tuesday,   u.scheduled_end_tuesday),
  (3, 'Mi', u.scheduled_start_wednesday, u.scheduled_end_wednesday),
  (4, 'Do', u.scheduled_start_thursday,  u.scheduled_end_thursday),
  (5, 'Fr', u.scheduled_start_friday,    u.scheduled_end_friday)
) AS d(nr, tag, beginn, ende)
WHERE d.beginn IS NOT NULL OR d.ende IS NOT NULL
ORDER BY u.tenant_id, u.username, d.nr;

-- Q2: Zusammenfassung je Befund
WITH f AS (
  SELECT CASE
           WHEN d.beginn IS NULL OR d.ende IS NULL THEN 'halboffen'
           WHEN d.beginn >= d.ende THEN 'Beginn>=Ende'
           WHEN EXTRACT(SECOND FROM d.beginn) <> 0 OR EXTRACT(SECOND FROM d.ende) <> 0 THEN 'Sekunden'
           ELSE 'ok'
         END AS befund
  FROM users u
  CROSS JOIN LATERAL (VALUES
    (u.scheduled_start_monday,    u.scheduled_end_monday),
    (u.scheduled_start_tuesday,   u.scheduled_end_tuesday),
    (u.scheduled_start_wednesday, u.scheduled_end_wednesday),
    (u.scheduled_start_thursday,  u.scheduled_end_thursday),
    (u.scheduled_start_friday,    u.scheduled_end_friday)
  ) AS d(beginn, ende)
  WHERE d.beginn IS NOT NULL OR d.ende IS NOT NULL
)
SELECT befund, COUNT(*) AS fenster FROM f GROUP BY befund ORDER BY befund;

-- Q3: Umfang des Backfills — Konten mit Fenster, Verlaufszeilen, Stundenzählung
SELECT u.tenant_id, u.username, u.track_hours, u.use_daily_schedule,
       (SELECT COUNT(*) FROM working_hours_changes w WHERE w.user_id = u.id) AS verlaufszeilen
FROM users u
WHERE COALESCE(u.scheduled_start_monday, u.scheduled_end_monday,
               u.scheduled_start_tuesday, u.scheduled_end_tuesday,
               u.scheduled_start_wednesday, u.scheduled_end_wednesday,
               u.scheduled_start_thursday, u.scheduled_end_thursday,
               u.scheduled_start_friday, u.scheduled_end_friday) IS NOT NULL
ORDER BY u.tenant_id, u.username;

-- Q4: Fenster kürzer als das (heutige) Tagessoll — informativ, mit E10/E18 unkritisch
SELECT u.username, d.tag,
       ROUND(EXTRACT(EPOCH FROM (d.ende - d.beginn)) / 3600, 2) AS fenster_h,
       ROUND(CASE WHEN u.use_daily_schedule THEN COALESCE(d.std, 0)
                  ELSE u.weekly_hours / NULLIF(u.work_days_per_week, 0) END, 2) AS tagessoll_h
FROM users u
CROSS JOIN LATERAL (VALUES
  ('Mo', u.scheduled_start_monday,    u.scheduled_end_monday,    u.hours_monday),
  ('Di', u.scheduled_start_tuesday,   u.scheduled_end_tuesday,   u.hours_tuesday),
  ('Mi', u.scheduled_start_wednesday, u.scheduled_end_wednesday, u.hours_wednesday),
  ('Do', u.scheduled_start_thursday,  u.scheduled_end_thursday,  u.hours_thursday),
  ('Fr', u.scheduled_start_friday,    u.scheduled_end_friday,    u.hours_friday)
) AS d(tag, beginn, ende, std)
WHERE d.beginn IS NOT NULL AND d.ende IS NOT NULL AND d.beginn < d.ende
  AND EXTRACT(EPOCH FROM (d.ende - d.beginn)) / 3600
      < CASE WHEN u.use_daily_schedule THEN COALESCE(d.std, 0)
             ELSE u.weekly_hours / NULLIF(u.work_days_per_week, 0) END
ORDER BY u.username, d.tag;

-- Q5: Einträge exakt auf der alten Fensterkante ohne Rohstempel
--     (später „nicht erweiterbar", E50)
WITH g AS (
  SELECT t.id AS tenant_id,
         COALESCE((SELECT NULLIF(s.value, '')::int FROM system_settings s
                   WHERE s.tenant_id = t.id AND s.key = 'work_window_grace_minutes'), 15) AS grace
  FROM tenants t
), w AS (
  SELECT u.id AS user_id, u.username, u.tenant_id, d.isodow, d.beginn, d.ende
  FROM users u
  CROSS JOIN LATERAL (VALUES
    (1, u.scheduled_start_monday,    u.scheduled_end_monday),
    (2, u.scheduled_start_tuesday,   u.scheduled_end_tuesday),
    (3, u.scheduled_start_wednesday, u.scheduled_end_wednesday),
    (4, u.scheduled_start_thursday,  u.scheduled_end_thursday),
    (5, u.scheduled_start_friday,    u.scheduled_end_friday)
  ) AS d(isodow, beginn, ende)
  WHERE d.beginn IS NOT NULL OR d.ende IS NOT NULL
)
SELECT w.username,
       COUNT(*) FILTER (WHERE e.raw_start_time IS NULL
                          AND e.start_time = w.beginn - make_interval(mins => g.grace)) AS beginn_auf_kante,
       COUNT(*) FILTER (WHERE e.raw_end_time IS NULL
                          AND e.end_time = w.ende + make_interval(mins => g.grace))     AS ende_auf_kante,
       COUNT(*) FILTER (WHERE e.raw_start_time IS NOT NULL OR e.raw_end_time IS NOT NULL) AS mit_rohstempel
FROM w
JOIN g ON g.tenant_id = w.tenant_id
JOIN time_entries e ON e.user_id = w.user_id AND EXTRACT(ISODOW FROM e.date) = w.isodow
GROUP BY w.username
ORDER BY w.username;

-- Q6: Puffer je Mandant
SELECT t.id, t.name,
       COALESCE((SELECT s.value FROM system_settings s
                 WHERE s.tenant_id = t.id AND s.key = 'work_window_grace_minutes'), '15 (Default)') AS puffer
FROM tenants t ORDER BY t.name;
