-- MQTT Benchmark: один send на N событий
-- Проверка гипотезы: нагружает количество publish, а не объём данных
-- Топик cm-bench/<device>/events/batch
-- Вставить как скрипт в LogicMachine и запустить вручную
-- Отредактируйте переменные ниже под свой брокер

local json = require('json')
local mqtt = require('mosquitto')

-- === Настройки (отредактировать) ===
local mqtt_host = 'elion.black-castle.ru'
local mqtt_port = 8883
local mqtt_username = 'cottage_client'   -- ваш логин
local mqtt_password = 'ваш_пароль'       -- ваш пароль
local device_id = 'bench'

-- Корневой топик для бенчмарка (отдельно от cm/)
local base_topic = 'cm-bench/' .. device_id .. '/events/batch'

local SIZES = { 10, 50, 100, 200, 500 }
local seq = 0

local function make_event()
  seq = seq + 1
  return {
    ts = os.time(),
    seq = seq,
    type = 'knx.groupwrite',
    ga = '1/1/1',
    id = 1,
    name = 'Bench object',
    datatype = 0,
    value = math.random(0, 100)
  }
end

local function run_benchmark()
  if mqtt_host == '' or mqtt_username == '' or mqtt_password == '' then
    log('CM bench: задайте mqtt_host, mqtt_username, mqtt_password в cottage-monitoring')
    return
  end

  local cid = 'cm-bench-' .. os.time()
  local client = mqtt.new(cid, true)
  client:login_set(mqtt_username, mqtt_password)
  client:version_set(mqtt.PROTOCOL_V311)
  client:tls_insecure_set(true)

  local connected = false
  client:callback_set('ON_CONNECT', function()
    connected = true
  end)

  client:connect(mqtt_host, mqtt_port, 60)

  -- Ждём подключения (до 5 сек)
  for _ = 1, 50 do
    client:loop(100)
    if connected then break end
    os.sleep(0.1)
  end

  if not connected then
    log('CM bench: не удалось подключиться к MQTT')
    return
  end

  log('CM bench: подключено, отправка пакетов 10, 50, 100, 200, 500 событий (один send на пакет)')

  for _, n in ipairs(SIZES) do
    local events = {}
    for i = 1, n do
      table.insert(events, make_event())
    end
    local payload = json.encode(events)
    local sec0, usec0 = os.microtime()

    client:publish(base_topic, payload, 0, false)

    local dur = os.udifftime(sec0, usec0)
    local size_bytes = #payload
    log(string.format('CM bench: n=%d dur=%.3fs size=%d bytes', n, dur, size_bytes))
  end

  client:disconnect()
  client:loop(100)
  log('CM bench: готово')
end

run_benchmark()
