-- Cottage Monitoring MQTT Client Daemon v1.1.1
-- Compact MQTT+cmd+meta+localbus. Always pump loop(); treat only numeric nonzero as error.
storage.set('cm_force_restart', nil)
storage.set('cm_started_ts', os.time())
storage.set('cm_heartbeat', os.time())
storage.set('cm_mqtt_connected', false)
storage.set('mqtt_connected', false)
storage.set('cm_last_error', '')
storage.set('cm_reconnect_count', 0)
storage.set('cm_boot', 'v111b_start')

local config = require('config')
local json = require('json')
local mqtt = require('mosquitto')
local grp = grp
local lb = require('localbus').new(0.5)

local RECONNECT_MIN, RECONNECT_MAX, KEEPALIVE = 2, 60, 60
local CHUNK_SIZE, HEALTH_INTERVAL = 100, 60

local function cfg(k, d) return config.get('cottage-monitoring', k, d) end
local function set_err(e) pcall(storage.set, 'cm_last_error', tostring(e or '')) end
local function loop_failed(rc)
  -- LM binding: success may be true/nil/0; only numeric ~= 0 is an error
  return type(rc) == 'number' and rc ~= 0
end

local C = {
  house_id = cfg('house_id', '') or '',
  device_id = cfg('device_id', '') or '',
  env_mode = cfg('env_mode', 'prod') or 'prod',
  mqtt_host = cfg('mqtt_host', '') or '',
  mqtt_port = tonumber(cfg('mqtt_port', 8883)) or 8883,
  mqtt_username = cfg('mqtt_username', '') or '',
  mqtt_password = cfg('mqtt_password', '') or '',
  client_id = cfg('client_id', '') or '',
  buffer_size = tonumber(cfg('buffer_size', 1000)) or 1000,
  loop_sleep = tonumber(cfg('loop_sleep', 0.15)) or 0.15,
  throttle = tonumber(cfg('throttle', 30)) or 30,
  event_sleep = tonumber(cfg('event_sleep', 0.02)) or 0.02,
}
if C.client_id == '' or C.client_id == 'auto' then C.client_id = C.house_id .. '-' .. C.device_id end
C.base = ((C.env_mode == 'dev') and 'dev/' or '') .. 'cm/' .. C.house_id .. '/' .. C.device_id .. '/v1/'

local S = {
  client = nil, connected = false, seq = 0,
  reconnect_delay = RECONNECT_MIN,
  reconnect_count = 0,
  next_reconnect_ts = 0, started_ts = os.time(),
  last_health_pub_ts = 0, meta_sent = false,
  last_evt_ts = 0, evt_count = 0,
}
local buffer = {}

local function hb()
  pcall(storage.set, 'cm_heartbeat', os.time())
  pcall(storage.set, 'cm_mqtt_connected', S.connected and true or false)
  pcall(storage.set, 'mqtt_connected', S.connected and true or false)
end

local function do_pub(rel, payload, qos, retain)
  local full = C.base .. rel
  if S.connected and S.client then
    pcall(function() S.client:publish(full, payload, qos or 1, retain or false) end)
  elseif C.buffer_size > 0 then
    table.insert(buffer, { topic = full, payload = payload, qos = qos or 1, retain = retain or false })
    while #buffer > C.buffer_size do table.remove(buffer, 1) end
  end
end

local function publish_meta()
  local all = grp.all() or {}
  local sorted = {}
  for _, o in ipairs(all) do if o.address then table.insert(sorted, o) end end
  table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)
  local addrs = {}
  for _, o in ipairs(sorted) do table.insert(addrs, o.address or '') end
  local schema_hash = ''
  local ok, encdec = pcall(require, 'encdec')
  if ok and encdec and encdec.sha256 then schema_hash = 'sha256:' .. (encdec.sha256(json.encode(addrs)) or '') end
  local count, ts = #sorted, os.time()
  local function fmt(o)
    return { id = o.id, address = o.address or '', name = o.name or '', datatype = o.datatype or 0,
      units = o.units or '', tags = o.tagcache or o.tags or '', comment = o.comment or '' }
  end
  if count <= CHUNK_SIZE then
    local objects = {}
    for _, o in ipairs(sorted) do table.insert(objects, fmt(o)) end
    do_pub('meta/objects', json.encode({ ts = ts, schema_version = 1, schema_hash = schema_hash, count = count, objects = objects }), 1, true)
  else
    local total = math.ceil(count / CHUNK_SIZE)
    for n = 1, total do
      local a, b = (n - 1) * CHUNK_SIZE + 1, math.min(n * CHUNK_SIZE, count)
      local objects = {}
      for i = a, b do table.insert(objects, fmt(sorted[i])) end
      do_pub('meta/objects/chunk/' .. n, json.encode({ ts = ts, schema_version = 1, schema_hash = schema_hash, count = count, chunk_no = n, chunk_total = total, objects = objects }), 1, true)
      if n < total then os.sleep(0.02) end
    end
  end
  local pub_cnt = 0
  for _, o in ipairs(sorted) do
    local val = o.value
    if val == nil then local okv, v = pcall(grp.getvalue, o.address); val = okv and v or nil end
    do_pub('state/ga/' .. (o.address or ''):gsub('/', '-'), json.encode({ ts = ts, value = val, datatype = o.datatype or 0 }), 1, true)
    pub_cnt = pub_cnt + 1
    if pub_cnt >= 30 then pub_cnt = 0; os.sleep(0.02) end
  end
end

local function setup_client()
  local client = mqtt.new(C.client_id, true)
  client:login_set(C.mqtt_username, C.mqtt_password)
  client:version_set(mqtt.PROTOCOL_V311)
  pcall(function() client:tls_insecure_set(true) end)
  client:will_set(C.base .. 'status/offline', json.encode({ ts = os.time(), status = 'offline' }), 1, true)
  client:callback_set('ON_CONNECT', function()
    S.connected = true
    S.reconnect_delay = RECONNECT_MIN
    S.next_reconnect_ts = 0
    pcall(storage.set, 'cm_last_connect_ts', os.time())
    pcall(storage.set, 'cm_boot', 'ON_CONNECT')
    pcall(storage.set, 'cm_last_error', '')
    hb()
    pcall(function()
      client:publish(C.base .. 'status/online', json.encode({ ts = os.time(), status = 'online', device_id = C.device_id, version = '1.1.1' }), 1, true)
      client:subscribe(C.base .. 'cmd', 1)
      client:subscribe(C.base .. 'rpc/req/' .. C.client_id, 1)
      for _, e in ipairs(buffer) do client:publish(e.topic, e.payload, e.qos, e.retain) end
    end)
    buffer = {}
  end)
  client:callback_set('ON_DISCONNECT', function()
    S.connected = false
    pcall(storage.set, 'cm_last_disconnect_ts', os.time())
    pcall(storage.set, 'cm_boot', 'ON_DISCONNECT')
    hb()
  end)
  client:callback_set('ON_MESSAGE', function(mid, topic, payload)
    if topic:match('/cmd$') then
      local ok, msg = pcall(json.decode, payload)
      if not ok or not msg then return end
      local items = msg.items
      if not items and msg.ga ~= nil then items = { { ga = msg.ga, value = msg.value } } end
      if not items then return end
      local results = {}
      for _, it in ipairs(items) do
        local rok, rerr = pcall(grp.write, it.ga, it.value)
        table.insert(results, { ga = it.ga, applied = rok and true or false, error = rok and nil or tostring(rerr) })
      end
      do_pub('cmd/ack', json.encode({ request_id = msg.request_id, results = results, ts = os.time() }), 1, false)
    elseif topic:match('/rpc/req/') then
      local ok, msg = pcall(json.decode, payload)
      if not ok or not msg then return end
      local req_id = msg.request_id or ''
      local rpc_cid = topic:match('/rpc/req/([^/]+)')
      if rpc_cid then
        pcall(publish_meta)
        do_pub('rpc/resp/' .. rpc_cid .. '/' .. req_id, json.encode({ request_id = req_id, ok = true }), 0, false)
      end
    end
  end)
  return client
end


lb:sethandler('groupwrite', function(event)
  if C.throttle > 0 then
    local now = os.time()
    if now ~= S.last_evt_ts then S.last_evt_ts = now; S.evt_count = 0 end
    S.evt_count = S.evt_count + 1
    if S.evt_count > C.throttle then return end
  end
  local dst = event.dst or event.dstraw
  local obj = grp.find(dst)
  if not obj then return end
  local val = event.value
  if val == nil then local okv, v = pcall(grp.getvalue, dst); val = okv and v or nil end
  local ts = os.time()
  S.seq = S.seq + 1
  do_pub('events', json.encode({ ts = ts, seq = S.seq, type = 'knx.groupwrite', ga = obj.address or dst,
    id = obj.id, name = obj.name, datatype = obj.datatype or 0, value = val }), 0, false)
  do_pub('state/ga/' .. tostring(obj.address or dst):gsub('/', '-'),
    json.encode({ ts = ts, value = val, datatype = obj.datatype or 0 }), 1, true)
  if C.event_sleep > 0 then os.sleep(C.event_sleep) end
end)

S.client = setup_client()
hb()
pcall(function() S.client:connect(C.mqtt_host, C.mqtt_port, KEEPALIVE) end)

while true do
  local ok_iter, err_iter = pcall(function()
    if storage.get('cm_force_restart') then storage.set('cm_force_restart', nil); error('cm_force_restart') end
    hb()
    lb:step()
    local lok, lrc = pcall(function() return S.client:loop(100) end)
    if not lok then
      S.connected = false
      set_err('loop_ex:' .. tostring(lrc))
      S.next_reconnect_ts = os.time() + S.reconnect_delay
    elseif loop_failed(lrc) then
      S.connected = false
      set_err('loop_rc=' .. tostring(lrc))
      S.next_reconnect_ts = os.time() + S.reconnect_delay
    end
    if not S.connected then
      local now = os.time()
      if now >= S.next_reconnect_ts then
        S.reconnect_count = S.reconnect_count + 1
        pcall(storage.set, 'cm_reconnect_count', S.reconnect_count)
        pcall(storage.set, 'cm_boot', 'reconnect#' .. S.reconnect_count)
        pcall(function()
          if S.client.reconnect then
            local rc = S.client:reconnect()
            if type(rc) == 'number' and rc ~= 0 then S.client:connect(C.mqtt_host, C.mqtt_port, KEEPALIVE) end
          else
            S.client:connect(C.mqtt_host, C.mqtt_port, KEEPALIVE)
          end
        end)
        S.next_reconnect_ts = now + S.reconnect_delay
        S.reconnect_delay = math.min(S.reconnect_delay * 2, RECONNECT_MAX)
      end
    end
    if S.connected and not S.meta_sent then S.meta_sent = true; pcall(publish_meta) end
    if S.connected and (os.time() - S.last_health_pub_ts) >= HEALTH_INTERVAL then
      do_pub('status/health', json.encode({
        ts = os.time(), status = 'online', version = '1.1.1',
        uptime = os.time() - S.started_ts, reconnects = S.reconnect_count, mqtt_connected = true,
      }), 1, true)
      S.last_health_pub_ts = os.time()
    end
  end)
  if not ok_iter then
    set_err(tostring(err_iter))
    if tostring(err_iter):find('cm_force_restart') then error(err_iter) end
  end
  os.sleep(C.loop_sleep)
end
