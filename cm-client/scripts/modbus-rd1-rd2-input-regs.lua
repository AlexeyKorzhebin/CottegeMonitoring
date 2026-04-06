--[[
  modbus-rd1-rd2-input-regs.lua
  Опрос Razumdom (rd1/rd2): Modbus Input Registers → KNX 1/3/* (DPT 9), без промежуточных 32/3/*.

  Алгоритм
  --------
  • На каждый DEVICES: tcp() → open(host,port) → connect() → setslave(unit_id) → FC04 → close().
    Для Modbus TCP на LM после open нужен connect() (форум/KB), иначе Bad file descriptor.
  • READ_STRATEGY 'block' — один readinputregisters(start,n); 'single' — по одному адресу (док.RD).
    Блочный ответ на части LM — N чисел как N return values; скрипт собирает в таблицу.
  • Температура: value = mult * (raw - raw_zero) / div (таблица CAL; в outputs можно mult/raw_zero/div).
  • Запись: grp.checkupdate(addr, value, delta) — третий аргумент: минимальная дельта (°C) для обновления шины.

  API: docs/LogicMachine Modbus RTU Master Lua API.pdf + tcp()/connect() для TCP.

  Логирование (LOG_VERBOSE)
  --------------------------
  false (продакшен): только ошибки (чтение Modbus, TCP, pcall).
  true (отладка): сводки raw_registers, строка на каждый grp, замеры modbus_only и main() dur.
]]

-- Глобальная калибровка: grp.checkupdate('1/3/?', 20 * (x - 2258) / 145)
local CAL = {
    mult = 20,
    raw_zero = 2258,
    div = 145,
}

-- 'block' — readinputregisters(start, n) одним запросом (PDF LogicMachine).
-- 'single' — readinputregisters(addr) только с ОДНИМ аргументом, по док.RD; n раз подряд.
local READ_STRATEGY = 'block'

-- nil = читать все d.count; 1 = тест одного регистра (обновится только outputs[1]).
local REGISTER_LIMIT = nil

-- setresponsetimeout не в PDF; при «Bad file descriptor» оставьте false.
local USE_SETRESPONSE_TIMEOUT = false

-- false — только log при ошибках (продакшен).
-- true — отладка: raw_registers, каждый grp, строки modbus_only / main() dur.
local LOG_VERBOSE = false

local function dbg(msg)
    if LOG_VERBOSE then
        log(msg)
    end
end

local function discard(...)
end

-- Минимальное |ΔT| (°C) для записи в KNX; 3-й параметр grp.checkupdate (LogicMachine). 0 — на каждое изменение.
local GRP_CHECKUPDATE_DELTA_DEG = 0.5

local DEVICES = {
    {
        host = '192.168.100.21',
        port = 502,
        unit_id = 21,
        start_ir = 11,
        count = 8,
        outputs = {
            { addr = '1/3/13' }, -- IR11
            { addr = '1/3/3' },  -- IR12
            { addr = '1/3/4' },  -- IR13
            { addr = '1/3/5' },  -- IR14
            { addr = '1/3/6' },  -- IR15
            { addr = '1/3/7' },  -- IR16
            { addr = '1/3/8' },  -- IR17
            { addr = '1/3/12' }, -- IR18
        },
    },
    {
        host = '192.168.100.22',
        port = 502,
        unit_id = 22,
        start_ir = 11,
        count = 6,
        outputs = {
            { addr = '1/3/2' },  -- IR11
            { addr = '1/3/9' },  -- IR12
            { addr = '1/3/10' }, -- IR13
            { addr = '1/3/11' }, -- IR14
            { addr = '1/3/14' }, -- IR15
            { addr = '1/3/15' }, -- IR16
        },
    },
}

-- luamodbus иногда отдаёт регистры с индекса 0: в Lua 5.1 у такой таблицы #t == 0.
local function normalize_registers(data, expected_count)
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

local function format_reg_list(data)
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

local function raw_to_value(raw, entry)
    local mult = entry.mult
    if mult == nil then
        mult = CAL.mult
    end
    local raw_zero = entry.raw_zero
    if raw_zero == nil then
        raw_zero = CAL.raw_zero
    end
    local div = entry.div
    if div == nil then
        div = CAL.div
    end
    return mult * (raw - raw_zero) / div
end

local function apply_outputs(outputs, data, unit_id)
    if type(data) ~= 'table' then
        return
    end
    local n = math.min(#data, #outputs)
    for i = 1, n do
        local entry = outputs[i]
        local addr = entry.addr
        local raw = data[i]
        if addr and raw ~= nil then
            local value = raw_to_value(raw, entry)
            dbg(
                'modbus-rd1-rd2 unit='
                    .. tostring(unit_id)
                    .. ' grp '
                    .. addr
                    .. ' ← raw='
                    .. tostring(raw)
                    .. ' value='
                    .. tostring(value)
                    .. ' (grp.checkupdate)'
            )
            discard(grp.checkupdate(addr, value, GRP_CHECKUPDATE_DELTA_DEG))
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

-- Док.RD: value = mb:readinputregisters(адрес) — один аргумент, одно значение.
local function read_input_registers_one_by_one(mb, start_ir, n)
    local data = {}
    for i = 1, n do
        local ra = start_ir + i - 1
        local v, err = mb:readinputregisters(ra)
        if v == nil then
            return nil, err, i, ra
        end
        if type(v) == 'table' then
            if #v >= 1 then
                v = v[1]
            elseif v[0] ~= nil then
                v = v[0]
            else
                return nil, 'readinputregisters: пустая таблица', i, ra
            end
        end
        data[i] = v
    end
    return data, nil
end

local function pack_multiresult(...)
    local argc = select('#', ...)
    local t = {}
    for i = 1, argc do
        t[i] = select(i, ...)
    end
    return t, argc
end

-- Блочный FC04: либо одна таблица (PDF), либо n чисел подряд как n return values (док.RD-стиль).
local function read_input_registers_block(mb, start_ir, n)
    local vals, argc = pack_multiresult(mb:readinputregisters(start_ir, n))
    if argc == 0 or vals[1] == nil then
        return nil, 'пустой ответ readinputregisters'
    end
    if argc == 1 and type(vals[1]) == 'table' then
        return vals[1], nil
    end
    if type(vals[1]) == 'number' then
        if argc < n then
            return nil, 'вернулось ' .. tostring(argc) .. ' знач., нужно ' .. tostring(n)
        end
        local data = {}
        for i = 1, n do
            local v = vals[i]
            if type(v) ~= 'number' then
                return nil, 'позиция ' .. tostring(i) .. ' не number: ' .. type(v)
            end
            data[i] = v
        end
        return data, nil
    end
    return nil, 'неожиданный ответ: argc=' .. tostring(argc) .. ' type1=' .. type(vals[1])
end

local function poll_device(mb, d, timing)
    local sr, ur
    if timing then
        sr, ur = os.microtime()
    end
    mb:setslave(d.unit_id)
    local n = d.count
    if REGISTER_LIMIT ~= nil then
        n = math.min(d.count, REGISTER_LIMIT)
    end

    local raw_data, read_err, fail_i, fail_ra
    if READ_STRATEGY == 'single' then
        raw_data, read_err, fail_i, fail_ra = read_input_registers_one_by_one(mb, d.start_ir, n)
    else
        raw_data, read_err = read_input_registers_block(mb, d.start_ir, n)
    end

    local data = normalize_registers(raw_data, n)
    if timing and sr then
        timing.modbus = timing.modbus + os.udifftime(sr, ur)
    end
    if raw_data == nil then
        log(
            'modbus-rd1-rd2 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' strategy='
                .. tostring(READ_STRATEGY)
                .. ' read → nil err='
                .. tostring(read_err)
                .. (fail_ra and (' @ir=' .. tostring(fail_ra) .. ' i=' .. tostring(fail_i)) or '')
        )
    elseif type(raw_data) ~= 'table' then
        log(
            'modbus-rd1-rd2 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' strategy='
                .. tostring(READ_STRATEGY)
                .. ' read ожидалась таблица после block, type='
                .. type(raw_data)
                .. ' detail='
                .. tostring(read_err)
        )
    elseif #raw_data == 0 and raw_data[0] == nil then
        log(
            'modbus-rd1-rd2 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' read пусто (#=0, нет [0]) err='
                .. tostring(read_err)
        )
    elseif raw_data ~= data then
        dbg(
            'modbus-rd1-rd2 '
                .. tostring(d.host)
                .. ' unit='
                .. tostring(d.unit_id)
                .. ' регистры с индекса 0 → 1..'
                .. tostring(n)
        )
    end
    dbg(
        'modbus-rd1-rd2 '
            .. tostring(d.host)
            .. ' unit='
            .. tostring(d.unit_id)
            .. ' strategy='
            .. tostring(READ_STRATEGY)
            .. ' n='
            .. tostring(n)
            .. ' start_ir='
            .. tostring(d.start_ir)
            .. ' raw_registers=['
            .. format_reg_list(data or raw_data)
            .. ']'
    )
    apply_outputs(d.outputs, data, d.unit_id)
end

local function main()
    local luamodbus = require('luamodbus')
    local timing = LOG_VERBOSE and { modbus = 0 } or nil
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
                        'modbus-rd1-rd2 '
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
                'modbus-rd1-rd2 tcp '
                    .. tostring(d.host)
                    .. ':'
                    .. tostring(d.port)
                    .. ' pcall: '
                    .. tostring(perr)
            )
        end
    end
    return timing
end

local sec0, usec0
if LOG_VERBOSE then
    sec0, usec0 = os.microtime()
end
local timing = main()
if LOG_VERBOSE and timing then
    local dur = os.udifftime(sec0, usec0)
    dbg(
        string.format(
            'modbus-rd1-rd2: modbus_only dur=%.6f s (~%.3f ms) (TCP+FC04+close, без grp)',
            timing.modbus,
            timing.modbus * 1000
        )
    )
    dbg(
        string.format(
            'modbus-rd1-rd2: main() dur=%.6f s (~%.3f ms) os.udifftime',
            dur,
            dur * 1000
        )
    )
end
