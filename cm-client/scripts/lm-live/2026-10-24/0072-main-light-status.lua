--[[
  modbus-drm88-coils-to-knx.lua
  Razumdom DRM88ER: чтение coils (FC01) → KNX (DPT 01.001 switch), опрос каждые POLL_INTERVAL_SEC.

  Алгоритм
  --------
  • На каждый DEVICES: tcp() → open(host,port) → connect() → setslave(unit_id) → readcoils(start, n) → close().
  • Таблица outputs — явное соответствие: строка i = канал COILi (i = 1…8) → заданный GA; readcoils(start_coil, 8) читает 8 бит подряд.
  • Один проход на вызов: опрос всех DEVICES, в конце os.sleep(POLL_INTERVAL_SEC). Резидентный режим включает сама LogicMachine.
  • Запись: grp.checkupdate(addr, value) — без третьего аргумента для 0/1: по KB для целых delta по умолчанию 1,
    обновление только при смене 0↔1 (частый опрос не «дёргает» шину/объект). Не задавать delta=0: при |Δ|>=0 условие
    истинно всегда. См. https://kb.logicmachine.net/libraries/lua/ (grp.checkupdate / grp.checkwrite).

  DRM88ER: нумерация выходов COIL1…COIL8. При нумерации адресов с 1 — start_coil = 1; если библиотека/карта даёт первый выход как 0 — start_coil = 0.
  На LM чаще mb:readcoils(start, qty); если нет метода — mb:read_bits(start, qty) (заменить в read_coils_*).

  Диагностика: ENABLE_DIAGNOSTICS = true — лог по каждому grp, сырые coils, длительности Modbus/раунда.

  Объекты в LM: GA 1/2/1…1/2/16 под DPT 01.001 (switch), теги вроде light/status — для фильтров и логики в других скриптах.
  Этот скрипт не вызывает grp.tag(): порядок объектов по тегу не совпадает с порядком COIL1…8 на шлюзе, плюс два хоста.
  GA 1/2/17… и выше (например zigbee) сюда не входят — не полнятся из Modbus.

  API: luamodbus (LogicMachine), как modbus-rd1-rd2-input-regs.lua.
]]

-- Пауза в конце одного прохода (сек); при резидентном запуске на LM задаёт интервал между опросами. 0.5 → 500 ms.
local POLL_INTERVAL_SEC = 0.5

local USE_SETRESPONSE_TIMEOUT = false

-- true — подробный log (каждый grp.checkupdate, список coils, время Modbus и раунда).
local ENABLE_DIAGNOSTICS = false

-- nil = читать все coils; 1 — отладка одного бита.
local COIL_LIMIT = nil

local function dbg(msg)
    if ENABLE_DIAGNOSTICS then
        log(msg)
    end
end

local function discard(...)
end

local DEVICES = {
    {
        host = '192.168.100.23',
        port = 502,
        unit_id = 23,
        start_coil = 1,
        count = 8,
        outputs = {
            { addr = '1/2/1' }, -- COIL1
            { addr = '1/2/2' }, -- COIL2
            { addr = '1/2/3' }, -- COIL3
            { addr = '1/2/4' }, -- COIL4
            { addr = '1/2/5' }, -- COIL5
            { addr = '1/2/6' }, -- COIL6
            { addr = '1/2/7' }, -- COIL7
            { addr = '1/2/8' }, -- COIL8
        },
    },
    {
        host = '192.168.100.24',
        port = 502,
        unit_id = 24,
        start_coil = 1,
        count = 8,
        outputs = {
            { addr = '1/2/9' },  -- COIL1
            { addr = '1/2/10' }, -- COIL2
            { addr = '1/2/11' }, -- COIL3
            { addr = '1/2/12' }, -- COIL4
            { addr = '1/2/13' }, -- COIL5
            { addr = '1/2/14' }, -- COIL6
            { addr = '1/2/15' }, -- COIL7
            { addr = '1/2/16' }, -- COIL8
        },
    },
}

local function normalize_bits(data, expected_count)
    if type(data) ~= 'table' then
        return nil
    end
    if #data > 0 then
        return data
    end
    if data[0] == nil then
        return data
    end
    local t = {}
    for i = 1, expected_count do
        t[i] = data[i - 1]
    end
    return t
end

local function format_bit_list(data)
    if type(data) ~= 'table' then
        return tostring(data)
    end
    local parts = {}
    local n = #data
    if n > 0 then
        for i = 1, n do
            parts[i] = tostring(data[i])
        end
        return table.concat(parts, ', ')
    end
    if data[0] ~= nil then
        local i = 0
        while data[i] ~= nil do
            parts[#parts + 1] = tostring(data[i])
            i = i + 1
        end
        return table.concat(parts, ', ')
    end
    return ''
end

-- Coil → DPT 01.001: только 0/1 (luamodbus может отдать number или boolean).
local function coil_to_switch(raw)
    local t = type(raw)
    if t == 'boolean' then
        return raw and 1 or 0
    end
    if t == 'number' then
        return (raw ~= 0) and 1 or 0
    end
    return nil
end

local function apply_switch_outputs(outputs, data, unit_id)
    if type(data) ~= 'table' then
        return
    end
    local n = math.min(#data, #outputs)
    for i = 1, n do
        local entry = outputs[i]
        local addr = entry.addr
        local raw = data[i]
        local val = coil_to_switch(raw)
        if addr and val ~= nil then
            dbg(
                'modbus-drm88 unit='
                    .. tostring(unit_id)
                    .. ' grp '
                    .. addr
                    .. ' ← coil='
                    .. tostring(raw)
                    .. ' → '
                    .. tostring(val)
                    .. ' (grp.checkupdate)'
            )
            -- delta не передаём: для целых по умолчанию 1 — без смены 0/1 нет обновления (KB LM). delta=0 обновляло бы каждый раз.
            discard(grp.checkupdate(addr, val))
        end
    end
end

local function safe_close(mb)
    pcall(function()
        if mb and mb.close then
            mb:close()
        end
    end)
end

local function pack_multiresult(...)
    local argc = select('#', ...)
    local t = {}
    for i = 1, argc do
        t[i] = select(i, ...)
    end
    return t, argc
end

local function read_coils_block(mb, start_coil, n)
    local vals, argc = pack_multiresult(mb:readcoils(start_coil, n))
    if argc == 0 or vals[1] == nil then
        return nil, 'пустой ответ readcoils'
    end
    if argc == 1 and type(vals[1]) == 'table' then
        return vals[1], nil
    end
    if argc < n then
        return nil, 'вернулось ' .. tostring(argc) .. ' знач., нужно ' .. tostring(n)
    end
    local data = {}
    for i = 1, n do
        local v = vals[i]
        local tv = type(v)
        if tv ~= 'number' and tv ~= 'boolean' then
            return nil, 'coil i=' .. tostring(i) .. ': ожидалось 0/1 или boolean, type=' .. tv
        end
        data[i] = v
    end
    return data, nil
end

local function poll_device(mb, d, timing)
    local sr, ur
    if timing then
        sr, ur = os.microtime()
    end
    mb:setslave(d.unit_id)
    local n = d.count
    if COIL_LIMIT ~= nil then
        n = math.min(d.count, COIL_LIMIT)
    end

    local raw_data, read_err = read_coils_block(mb, d.start_coil, n)

    local data = normalize_bits(raw_data, n)
    if timing and sr then
        timing.modbus = timing.modbus + os.udifftime(sr, ur)
    end
    if raw_data == nil then
        log(
            'modbus-drm88 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' readcoils → nil err='
                .. tostring(read_err)
        )
    elseif type(raw_data) ~= 'table' then
        log(
            'modbus-drm88 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' после block ожидалась таблица, type='
                .. type(raw_data)
                .. ' detail='
                .. tostring(read_err)
        )
    elseif #raw_data == 0 and raw_data[0] == nil then
        log(
            'modbus-drm88 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' read пусто (#=0, нет [0]) err='
                .. tostring(read_err)
        )
    elseif raw_data ~= data then
        dbg(
            'modbus-drm88 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' биты с индекса 0 → 1..'
                .. tostring(n)
        )
    end
    dbg(
        'modbus-drm88 '
            .. tostring(d.host)
            .. ' unit='
            .. tostring(d.unit_id)
            .. ' n='
            .. tostring(n)
            .. ' start_coil='
            .. tostring(d.start_coil)
            .. ' coils=['
            .. format_bit_list(data or raw_data)
            .. ']'
    )
    apply_switch_outputs(d.outputs, data, d.unit_id)
end

local function main_round(timing)
    local luamodbus = require('luamodbus')
    for di = 1, #DEVICES do
        local d = DEVICES[di]
        local mb = luamodbus.tcp()
        local ok, perr = pcall(function()
            local st, ut
            if timing then
                st, ut = os.microtime()
            end
            mb:open(d.host, d.port)
            if mb.connect then
                local cres, cerr = mb:connect()
                if cerr ~= nil or cres == false then
                    if timing then
                        timing.modbus = timing.modbus + os.udifftime(st, ut)
                    end
                    log(
                        'modbus-drm88 '
                            .. tostring(d.host)
                            .. ':'
                            .. tostring(d.port)
                            .. ' tcp connect res='
                            .. tostring(cres)
                            .. ' err='
                            .. tostring(cerr)
                    )
                    return
                end
            end
            if mb.settimeout then
                mb:settimeout(2)
            end
            if USE_SETRESPONSE_TIMEOUT and mb.setresponsetimeout then
                mb:setresponsetimeout(2000)
            end
            if timing then
                timing.modbus = timing.modbus + os.udifftime(st, ut)
            end
            poll_device(mb, d, timing)
        end)
        local sc, uc
        if timing then
            sc, uc = os.microtime()
        end
        safe_close(mb)
        if timing and sc then
            timing.modbus = timing.modbus + os.udifftime(sc, uc)
        end
        if not ok then
            log(
                'modbus-drm88 tcp '
                    .. tostring(d.host)
                    .. ':'
                    .. tostring(d.port)
                    .. ' pcall: '
                    .. tostring(perr)
            )
        end
    end
end

local function maybe_log_diagnostics_round(timing)
    if not ENABLE_DIAGNOSTICS or not timing then
        return
    end
    dbg(
        string.format(
            'modbus-drm88: modbus_only dur=%.6f s (~%.3f ms)',
            timing.modbus,
            timing.modbus * 1000
        )
    )
end

local timing = ENABLE_DIAGNOSTICS and { modbus = 0 } or nil
local sec0, usec0
if ENABLE_DIAGNOSTICS then
    sec0, usec0 = os.microtime()
end
local ok, err = pcall(main_round, timing)
if not ok then
    log('modbus-drm88 pcall: ' .. tostring(err))
end
maybe_log_diagnostics_round(timing)
if ENABLE_DIAGNOSTICS and timing and sec0 then
    local dur = os.udifftime(sec0, usec0)
    dbg(
        string.format(
            'modbus-drm88: round dur=%.6f s (~%.3f ms)',
            dur,
            dur * 1000
        )
    )
end
os.sleep(POLL_INTERVAL_SEC)
