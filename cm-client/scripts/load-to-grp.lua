-- Load average → grp
-- Читает load average и записывает в три адреса (DPT 14 float).
--
-- Использование в LogicMachine:
-- 1. Создайте три объекта DPT 14 (float).
-- 2. Укажите адреса ниже.
-- 3. Вызовите скрипт по cron или вручную.

local GRP_LOAD_1  = '0/0/2'  -- load 1 min
local GRP_LOAD_5  = nil    -- '0/0/3' — load 5 min
local GRP_LOAD_15 = nil    -- '0/0/4' — load 15 min

local function get_load_average()
  local f = io.open('/proc/loadavg', 'r')
  if not f then return nil end
  local line = f:read('*l')
  f:close()
  if not line then return nil end
  local l1, l5, l15 = line:match('^([%d.]+)%s+([%d.]+)%s+([%d.]+)')
  return l1, l5, l15
end

local function main()
  local l1, l5, l15 = get_load_average()
  if not l1 then
    log('load-to-grp: не удалось прочитать load average')
    return
  end

  if grp and grp.update then
    if GRP_LOAD_1 and GRP_LOAD_5 and GRP_LOAD_15 then
      grp.update(GRP_LOAD_1, tonumber(l1) or 0)
      grp.update(GRP_LOAD_5, tonumber(l5) or 0)
      grp.update(GRP_LOAD_15, tonumber(l15) or 0)
      log('load-to-grp: обновлено в ' .. GRP_LOAD_1 .. ',' .. GRP_LOAD_5 .. ',' .. GRP_LOAD_15)
    end
  else
    log('load-to-grp: grp недоступен')
  end
end

main()
