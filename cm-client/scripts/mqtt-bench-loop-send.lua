-- MQTT Benchmark: N событий = N sends (цикл, как в daemon до batch)
-- Сравнение с mqtt-bench-single-send.lua: гипотеза — нагрузка от кол-ва publish
-- Топик cm-bench/<device>/events (одно событие = одно сообщение)
-- Вставить как скрипт в LogicMachine, отредактировать настройки ниже

local json = require('json')
local mqtt = require('mosquitto')

-- === Настройки (отредактировать) ===
local mqtt_host = 'elion.black-castle.ru'
local mqtt_port = 8883
local mqtt_username = 'cottage_client'   -- ваш логин
local mqtt_password = 'ваш_пароль'       -- ваш пароль
local device_id = 'bench'

local base_topic = 'cm-bench/' .. device_id .. '/events'
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
    log('CM bench-loop: задайте mqtt_host, mqtt_username, mqtt_password')
    return
  end

  local cid = 'cm-bench-loop-' .. os.time()
  local client = mqtt.new(cid, true)
  client:login_set(mqtt_username, mqtt_password)
  client:version_set(mqtt.PROTOCOL_V311)
  client:tls_insecure_set(true)

  local connected = false
  client:callback_set('ON_CONNECT', function()
    connected = true
  end)

  client:connect(mqtt_host, mqtt_port, 60)

  for _ = 1, 50 do
    client:loop(100)
    if connected then break end
    os.sleep(0.1)
  end

  if not connected then
    log('CM bench-loop: не удалось подключиться к MQTT')
    return
  end

  log('CM bench-loop: подключено, отправка 10, 50, 100, 200, 500 событий (один send на событие)')

  for _, n in ipairs(SIZES) do
    local sec0, usec0 = os.microtime()

    for i = 1, n do
      local evt = make_event()
      local payload = json.encode(evt)
      client:publish(base_topic, payload, 0, false)
    end

    local dur = os.udifftime(sec0, usec0)
    log(string.format('CM bench-loop: n=%d dur=%.3fs (%d sends)', n, dur, n))
  end

  client:disconnect()
  client:loop(100)
  log('CM bench-loop: готово')
end

run_benchmark()
