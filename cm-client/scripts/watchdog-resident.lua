-- =============================================================================
-- Cottage Monitoring — Resident watchdog (LogicMachine)
-- =============================================================================
-- КАК УСТАНОВИТЬ
--   Scripting → Resident → New script
--   Sleep interval: 60 секунд
--   Active: включён
--   Вставить этот файл целиком
--
-- ЗАЧЕМ НУЖЕН
--   Daemon Cottage Monitoring может «залипнуть»: процесс жив, но MQTT давно
--   не шлёт данные (типичная причина многонедельных пропусков в БД).
--   Штатный супервизор LM перезапускает daemon только при падении процесса.
--   Этот скрипт ловит именно случай «жив, но сломан» и делает жёсткий рестарт.
--
-- ОТКУДА БЕРЁТ СОСТОЯНИЕ
--   Daemon каждый цикл пишет в storage:
--     cm_heartbeat          — unix-время последней итерации цикла
--     cm_mqtt_connected     — true/false (есть ли MQTT)
--     cm_started_ts         — время старта daemon
--     cm_last_disconnect_ts — время последнего обрыва MQTT
--
-- ЛОГИКА (каждый запуск, ~раз в 60 с) — двухступенчатая эскалация
--   1) Проверить условия аварии (см. ниже). Если всё ок — сбросить эпизод
--      (cm_watchdog_soft_ts = 0) и выйти. Это значит, что soft-рестарт помог
--      или проблема сама ушла.
--   2) Авария обнаружена ВПЕРВЫЕ (cm_watchdog_soft_ts == 0) → только МЯГКИЙ путь:
--      cm_force_restart = 1. Если цикл daemon ещё живой, он сам сделает error()
--      и LM его перезапустит. Запоминаем время (cm_watchdog_soft_ts = now) и ждём
--      следующего вызова, чтобы проверить, помогло ли.
--   3) Авария ВСЁ ЕЩЁ есть на следующем вызове (прошло >= SOFT_ESCALATE_SEC, а
--      soft не помог — daemon завис и флаг не читает) → ЖЁСТКИЙ путь:
--      HTTP GET /apps/request.lp?action=restart&name=cottage-monitoring
--      (Referer + Basic Auth), убивает даже зависший процесс. Затем сбрасываем
--      эпизод, чтобы новая авария снова начиналась с мягкого пути.
--   4) Анти-флаппинг: жёсткий рестарт не чаще RESTART_COOLDOWN_SEC.
--
--   Смысл: soft даёт daemon шанс перезапуститься «мягко» без HTTP; hard
--   включается, только если soft за один цикл не помог (иначе soft был бы бесполезен).
--
-- УСЛОВИЯ АВАРИИ (достаточно одного)
--   • no_heartbeat     — heartbeat ещё ни разу не писался, а daemon стартовал
--                        больше HEARTBEAT_STALE_SEC назад
--   • heartbeat_stale  — последний heartbeat старше HEARTBEAT_STALE_SEC (120 с)
--   • mqtt_offline     — MQTT offline дольше MQTT_OFFLINE_RESTART_SEC (600 с = 10 мин)
--
-- ПОРОГИ
--   HEARTBEAT_STALE_SEC      = 120   — «daemon не отвечает»
--   MQTT_OFFLINE_RESTART_SEC = 600   — «долго без MQTT»
--   RESTART_COOLDOWN_SEC     = 300   — не чаще 1 рестарта / 5 минут
-- =============================================================================

local HEARTBEAT_STALE_SEC = 120
local MQTT_OFFLINE_RESTART_SEC = 600
local RESTART_COOLDOWN_SEC = 300
local SOFT_ESCALATE_SEC = 45   -- минимум между soft и hard (обычно = 1 циклу sleep)
local APP = 'cottage-monitoring'

-- Пароль веб-admin для HTTP hard-restart — только на контроллере (не в git):
--   Scripting console: config.set('cottage-monitoring', 'lm_admin_password', '…')
local config = require('config')
local LM_USER = tostring(config.get(APP, 'lm_admin_user', 'admin') or 'admin')
local LM_PASS = tostring(config.get(APP, 'lm_admin_password', '') or '')
local LM_HOST = '127.0.0.1'  -- сам на себя, с контроллера

local function now()
  return os.time()
end

local function get_num(key, default)
  local v = storage.get(key)
  if v == nil or v == '' then return default end
  return tonumber(v) or default
end

local function get_bool(key)
  local v = storage.get(key)
  return v == true or v == 'true' or v == 1 or v == '1'
end

-- Base64 для заголовка Authorization: Basic ...
local function b64(s)
  local ok, encdec = pcall(require, 'encdec')
  if ok and encdec and encdec.base64 then
    return encdec.base64(s)
  end
  local okm, mime = pcall(require, 'mime')
  if okm and mime and mime.b64 then
    return mime.b64(s)
  end
  return nil
end

-- Жёсткий рестарт daemon через Apps API.
-- Важно: LM требует заголовок Referer на себя, иначе 400/401.
local function hard_restart_daemon()
  if LM_PASS == '' then
    return false, 'set config lm_admin_password on LM (not in git)'
  end
  local http = require('socket.http')
  local ltn12 = require('ltn12')
  http.TIMEOUT = 10
  local auth = b64(LM_USER .. ':' .. LM_PASS)
  if not auth then
    return false, 'no base64 encoder'
  end
  local url = string.format(
    'http://%s/apps/request.lp?action=restart&name=%s',
    LM_HOST, APP
  )
  local sink = {}
  local body, code, err = http.request({
    url = url,
    method = 'GET',
    headers = {
      Authorization = 'Basic ' .. auth,
      Referer = 'http://' .. LM_HOST .. '/',
      ['User-Agent'] = 'cm-watchdog',
    },
    sink = ltn12.sink.table(sink),
  })
  local resp = table.concat(sink)
  if code == 200 then
    return true, resp
  end
  return false, string.format('http=%s err=%s body=%s', tostring(code), tostring(err), resp)
end

-- ----- Чтение состояния daemon -----
local hb = get_num('cm_heartbeat', 0)
local mqtt_ok = get_bool('cm_mqtt_connected') or get_bool('mqtt_connected')
local last_restart = get_num('cm_watchdog_last_restart', 0)
local t = now()
local reason = nil

-- ----- Диагностика: есть ли повод рестартовать? -----
if hb == 0 then
  -- Heartbeat ещё не писался. Ждём HEARTBEAT_STALE_SEC после старта,
  -- чтобы не сработать в момент обычной загрузки.
  local started = get_num('cm_started_ts', 0)
  if started > 0 and (t - started) > HEARTBEAT_STALE_SEC then
    reason = 'no_heartbeat'
  end
elseif (t - hb) > HEARTBEAT_STALE_SEC then
  -- Daemon не обновлял heartbeat — завис или умер.
  reason = string.format('heartbeat_stale age=%ds', t - hb)
elseif not mqtt_ok then
  -- Процесс жив, но MQTT давно offline (сценарий «залипшего» реконнекта).
  local offline_since = get_num('cm_last_disconnect_ts', 0)
  if offline_since == 0 then
    offline_since = get_num('cm_started_ts', 0)
  end
  if offline_since > 0 and (t - offline_since) >= MQTT_OFFLINE_RESTART_SEC then
    reason = string.format('mqtt_offline age=%ds', t - offline_since)
  end
end

-- Всё в порядке — сбрасываем эпизод (soft помог или проблема ушла) и выходим.
if not reason then
  if get_num('cm_watchdog_soft_ts', 0) ~= 0 then
    storage.set('cm_watchdog_soft_ts', 0)
    log('CM watchdog: fault cleared, episode reset')
  end
  return
end

local soft_ts = get_num('cm_watchdog_soft_ts', 0)

-- ===== Ступень 1: авария обнаружена впервые → только мягкий путь =====
-- Даём daemon шанс перезапуститься самому по флагу. Hard пока НЕ трогаем.
if soft_ts == 0 then
  storage.set('cm_watchdog_soft_ts', t)
  storage.set('cm_watchdog_last_reason', reason)
  storage.set('cm_force_restart', 1)
  alert(string.format('CM watchdog: soft restart requested reason=%s', reason))
  log(string.format('CM watchdog: soft flag set reason=%s (жду след. цикл для проверки)', reason))
  return
end

-- Мягкий путь был выставлен на прошлом вызове, но авария сохраняется.
-- Слишком рано? (защита, если sleep interval меньше ожидаемого) — ждём ещё.
if (t - soft_ts) < SOFT_ESCALATE_SEC then
  return
end

-- ===== Ступень 2: soft не помог → жёсткий HTTP-рестарт (с анти-флаппингом) =====
if last_restart > 0 and (t - last_restart) < RESTART_COOLDOWN_SEC then
  local last_alert = get_num('cm_watchdog_last_alert', 0)
  if (t - last_alert) >= RESTART_COOLDOWN_SEC then
    alert(string.format('CM watchdog: %s (cooldown, last hard restart %ds ago)', reason, t - last_restart))
    storage.set('cm_watchdog_last_alert', t)
  end
  return
end

local restarts = get_num('cm_watchdog_restarts', 0) + 1
storage.set('cm_watchdog_restarts', restarts)
storage.set('cm_watchdog_last_restart', t)
storage.set('cm_watchdog_last_alert', t)
storage.set('cm_watchdog_last_reason', reason)

local ok_http, http_detail = hard_restart_daemon()
storage.set('cm_watchdog_http_ok', ok_http and true or false)
storage.set('cm_watchdog_http_detail', tostring(http_detail or ''))

-- Сбрасываем эпизод: следующая авария снова начнётся с мягкого пути.
storage.set('cm_watchdog_soft_ts', 0)

if ok_http then
  alert(string.format('CM watchdog: hard restart #%d reason=%s (soft не помог)', restarts, reason))
  log(string.format('CM watchdog: hard restart #%d reason=%s http_ok detail=%s', restarts, reason, tostring(http_detail)))
else
  -- HTTP не удался — снова ставим мягкий флаг как последний шанс.
  storage.set('cm_force_restart', 1)
  alert(string.format('CM watchdog: HTTP restart FAILED #%d reason=%s (%s); soft flag set', restarts, reason, tostring(http_detail)))
  log(string.format('CM watchdog: HTTP restart failed #%d reason=%s detail=%s', restarts, reason, tostring(http_detail)))
end
