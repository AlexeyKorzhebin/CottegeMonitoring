-- ============================================================================
--  УПРАВЛЕНИЕ ПЛЕНОЧНЫМИ ТЕПЛЫМИ ПОЛАМИ (LogicMachine)
--  Версия: v3 (погодная добавка индивидуальная по комнатам + диагностика)
--
--  РЕЖИМЫ:
--   1) Нормальный (Zigbee свежий): управление по температуре воздуха (room)
--   2) Fallback (Zigbee протух): управление по температуре пола (floor)
--      через эффективную уставку:
--        effective_sp = setpoint + k + kw_base * w
--
--  Где:
--   setpoint - уставка пользователя (комнатная цель)
--   k        - комнатная постоянная поправка (воздух -> пол)
--   kw_base  - погодная добавка от внешней температуры
--   w        - коэффициент комнаты (этаж/сторона/угловая/витражи)
--
--  ЗАЩИТЫ:
--   A) Перегрев пола: floor_temp >= FLOOR_MAX_TEMP -> OFF
--   B) Долгий нагрев без Zigbee: Zigbee stale + relay ON долго -> OFF
--
--  Диагностика: пишем текст/числа в объекты диагностики
-- ============================================================================


-- ============================ ОБЩИЕ НАСТРОЙКИ ===============================

-- Переключатель автоуправления
local AUTO_GA = '1/7/1'
local auto_heating = grp.getvalue(AUTO_GA)

-- Лимит мощности на все полы (Вт)
local MAX_POWER_GA = 'Максимальный объем энергии для ТП'

-- Куда пишем текущую суммарную мощность включенных полов (Вт)
local USING_POWER_GA = 'Энергия на теплые полы'

-- Внешняя температура
local OUTDOOR_TEMP_OBJ = 'Погода - температура'

-- Свежесть Zigbee
local ZB_STALE_SEC = 300  -- 5 минуты

-- Защита по времени нагрева без Zigbee
local MAX_ON_SEC = 40 * 60  -- 40 минут

-- Гистерезис для Zigbee-режима
local HYST_ON  = 0.3
local HYST_OFF = 0.1

-- Защита по температуре пола
local FLOOR_MAX_TEMP = 34

-- Пауза между реле
local RELAY_DELAY_SEC = 0.2


-- ======================= ПОГОДНАЯ "КРИВАЯ" (база) ===========================
-- kw_base = (WEATHER_REF - Tout) * WEATHER_SLOPE, но не меньше 0, с ограничениями
local WEATHER_REF   = 0
local WEATHER_SLOPE = 0.30     -- твоя эмпирическая оценка (0 -> +0, -10 -> +3)
local WEATHER_MIN   = -25
local WEATHER_MAX   = 5
local WEATHER_K_MAX = 10       -- общий потолок добавки


-- ============================ ДИАГНОСТИКА ===================================
-- Эти объекты нужно создать в LogicMachine (как текстовые/строковые или числовые).
-- Если не хочешь заводить все - можно оставить только один текстовый.
local DIAG_TEXT_OBJ   = 'ТП Диагностика - текст'
local DIAG_MODE_OBJ   = 'ТП Диагностика - режимы'   -- например строка "zigbee=8 fallback=4"
local DIAG_BLOCK_OBJ  = 'ТП Диагностика - блоки'    -- например "overheat=0 long=1"
local DIAG_WEATHER_OBJ= 'ТП Диагностика - погода'   -- например "Tout=-12 kw=3.6"
local DIAG_POWER_OBJ  = 'ТП Диагностика - мощность' -- например "using=4200 limit=9000"


-- ========================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =========================


local function now()
  return os.time()
end

local function clamp(x, a, b)
  if x < a then return a end
  if x > b then return b end
  return x
end

local function to_number(v)
  if type(v) == 'number' then return v end
  if type(v) == 'string' then return tonumber(v) end
  return nil
end

local function has_updatetime(obj)
  return (obj ~= nil) and (type(obj.updatetime) == 'number')
end

-- Погодная добавка "базовая", без учета особенностей комнаты
local function weather_k_base(tout)
  tout = to_number(tout)
  if tout == nil then
    return 0
  end

  tout = clamp(tout, WEATHER_MIN, WEATHER_MAX)

  if tout >= WEATHER_REF then
    return 0
  end

  local k = (WEATHER_REF - tout) * WEATHER_SLOPE
  return clamp(k, 0, WEATHER_K_MAX)
end

-- Небольшая функция форматирования числа (для диагностики)
local function fmt1(x)
  if type(x) ~= 'number' then return 'n/a' end
  return string.format('%.1f', x)
end


-- ============================ ОПИСАНИЕ ПОЛОВ ================================
-- floor     : датчик температуры пола (аналог)
-- room      : Zigbee датчик температуры воздуха
-- setpoint  : уставка
-- ctrl      : реле
-- pow       : мощность (Вт)
-- prior     : приоритет
-- k         : поправка "воздух -> пол"
-- w         : коэффициент погоды для комнаты (0..2 обычно)
--
-- Примерные идеи для w:
--   0.7  - южная/внутренняя/тёплая комната
--   1.0  - обычная
--   1.2  - северная/угловая/первый этаж/большие окна
--   1.4+ - тамбур/холодная зона/витражи
local floors = {}

-- !!! room='...' заменить на реальные Zigbee объекты !!!
table.insert(floors, {name='тамбур',          floor='1/3/2',  room='ZB Тамбур Темп',        					setpoint='1/6/2',  ctrl='1/4/2',  pow=200,  prior=2, k=3, w=1.4})
table.insert(floors, {name='холл 1',          floor='1/3/3',  room='zb_sensor_fl1_hall_temperature',         	setpoint='1/6/3',  ctrl='1/4/3',  pow=1500, prior=3, k=5, w=1.0})
table.insert(floors, {name='спальня',         floor='1/3/4',  room='zb_sensor_fl1_bedroom_temperature',     	setpoint='1/6/4',  ctrl='1/4/4',  pow=1600, prior=2, k=5, w=1.4})
table.insert(floors, {name='гостиная 1',      floor='1/3/5',  room='zb_sensor_fl1_living_room_temperature',     setpoint='1/6/5',  ctrl='1/4/5',  pow=2200, prior=4, k=7, w=1.2})
table.insert(floors, {name='гостиная 2',      floor='1/3/6',  room='zb_sensor_fl1_living_room_temperature',     setpoint='1/6/6',  ctrl='1/4/6',  pow=200,  prior=4, k=7, w=1.2})
table.insert(floors, {name='кухня',           floor='1/3/7',  room='zb_sensor_fl1_kitchen_temperature',         setpoint='1/6/7',  ctrl='1/4/7',  pow=1450, prior=3, k=6, w=1.0})
table.insert(floors, {name='ванная 1',        floor='1/3/8',  room='zb_sensor_fl1_bathroom_temperature',       	setpoint='1/6/8',  ctrl='1/4/8',  pow=225,  prior=2, k=2, w=0.8})

table.insert(floors, {name='холл 2',          floor='1/3/10', room='zb_sensor_fl2_hall_temperature',         	setpoint='1/6/10', ctrl='1/4/10', pow=1200, prior=1, k=5, w=0.9})
table.insert(floors, {name='гостевая',        floor='1/3/11', room='zb_sensor_fl2_bedroom_temperature',       	setpoint='1/6/11', ctrl='1/4/11', pow=1000, prior=1, k=5, w=0.9})
table.insert(floors, {name='Настина комната', floor='1/3/12', room='zb_sensor_fl2_nastya_bedroom_temperature',  setpoint='1/6/12', ctrl='1/4/12', pow=2500, prior=1, k=6, w=1.0})
table.insert(floors, {name='Тимина комната',  floor='1/3/13', room='zb_sensor_fl2_tima_bedroom_temperature',    setpoint='1/6/13', ctrl='1/4/13', pow=1800, prior=1, k=6, w=1.0})
table.insert(floors, {name='ванная 2',        floor='1/3/14', room='zb_sensor_fl2_bathroom_temperature',       	setpoint='1/6/14', ctrl='1/4/14', pow=400,  prior=1, k=2, w=0.8})
table.insert(floors, {name='кабинет',         floor='1/3/15', room='zb_sensor_fl2_office_temperature',       	setpoint='1/6/15', ctrl='1/4/15', pow=775,  prior=3, k=6, w=1.1})



-- ===================== ЕСЛИ АВТОУПРАВЛЕНИЕ ВЫКЛЮЧЕНО ========================
if auto_heating == false then
  local status = storage.get('warm_floors.enable', true)

  if status == true then
    for _, f in ipairs(floors) do
      grp.update(f.ctrl, false, 1)
    end
    storage.set('warm_floors.enable', false)
  end

  -- Диагностика, чтобы было видно, что автологика отключена
  grp.update(DIAG_TEXT_OBJ, 'Автоуправление: ВЫКЛЮЧЕНО (полы отключены)')
  grp.update(DIAG_MODE_OBJ, 'auto=0')
  return
else
  storage.set('warm_floors.enable', true)
end


-- ============================ ОСНОВНАЯ ЛОГИКА ===============================

local tnow = now()
local allpower = grp.getvalue(MAX_POWER_GA)

-- Погодная база
local tout = grp.getvalue(OUTDOOR_TEMP_OBJ)
local kw_base = weather_k_base(tout)

-- Диагностические счетчики
local cnt_zigbee = 0
local cnt_fallback = 0
local cnt_overheat = 0
local cnt_longblock = 0
local cnt_on = 0



-- 1) Сбор параметров по каждой комнате
for i = 1, #floors do
  local f = floors[i]

  -- Уставка пользователя
  f.sp = grp.getvalue(f.setpoint)

  -- Температура пола
  f.floor_ct = grp.getvalue(f.floor)

  -- Zigbee температура воздуха
  local room_obj = grp.find(f.room)
  f.zb_ct = nil
  f.zb_age = 999999
  f.zb_ok = false

  if has_updatetime(room_obj) then
    f.zb_ct = to_number(room_obj.value)
    if f.zb_ct ~= nil then
      f.zb_age = tnow - room_obj.updatetime
      f.zb_ok = (f.zb_age <= ZB_STALE_SEC)
    end
  end

  -- Реле пола (для stateless таймера)
  local relay_obj = grp.find(f.ctrl)
  f.relay_on = false
  f.relay_age = 999999

  if has_updatetime(relay_obj) and type(relay_obj.value) == 'boolean' then
    f.relay_on = relay_obj.value
    f.relay_age = tnow - relay_obj.updatetime
  end

  -- Погодная добавка конкретной комнаты
  local w = to_number(f.w) or 1.0
  f.kw_room = kw_base * w

  -- Выбор режима
  if f.zb_ok then
    f.mode = 'zigbee'
    f.ctrl_temp = f.zb_ct
    f.effective_sp = f.sp
    cnt_zigbee = cnt_zigbee + 1
  else
    f.mode = 'floor_fallback'
    f.ctrl_temp = f.floor_ct
    f.effective_sp = f.sp + f.k + f.kw_room
    cnt_fallback = cnt_fallback + 1
  end

  --log('TP: ' .. f.name .. ' ' .. f.effective_sp)  
    
  -- Недогрев
  f.need = f.effective_sp - f.ctrl_temp
  if f.need < 0 then f.need = 0 end

  -- Защита A: перегрев пола
  f.floor_overheat = (type(f.floor_ct) == 'number') and (f.floor_ct >= FLOOR_MAX_TEMP)
  if f.floor_overheat then
    cnt_overheat = cnt_overheat + 1
  end

  -- Защита B: слишком долго греем без Zigbee
  f.long_on_without_zigbee = (not f.zb_ok) and f.relay_on and (f.relay_age >= MAX_ON_SEC)
  if f.long_on_without_zigbee then
    cnt_longblock = cnt_longblock + 1
  end
end


-- 2) Сортировка распределения мощности
local function sorter(a, b)
  if a.prior ~= b.prior then
    return a.prior > b.prior
  end
  if a.need ~= b.need then
    return a.need > b.need
  end
  return a.pow < b.pow
end

table.sort(floors, sorter)


-- 3) Применение (лимит мощности)
local using_power = 0



for _, f in ipairs(floors) do
  local want_on = false

  -- Безопасность важнее
  if f.floor_overheat then
    want_on = false
  elseif f.long_on_without_zigbee then
    want_on = false
  else
    if f.mode == 'zigbee' then
      -- Гистерезис по воздуху
      if f.ctrl_temp < (f.effective_sp - HYST_ON) then
        want_on = true
      elseif f.ctrl_temp > (f.effective_sp + HYST_OFF) then
        want_on = false
      else
        want_on = f.relay_on
      end
    else
      -- Fallback по полу (простое правило)
      want_on = (f.need > 0)
    end
  end

  -- Лимит мощности
  if want_on == false then
    grp.update(f.ctrl, false)
  else
    allpower = allpower - f.pow
    if allpower >= 0 then
      grp.update(f.ctrl, true)
      os.sleep(RELAY_DELAY_SEC)
      using_power = using_power + f.pow
      cnt_on = cnt_on + 1
    else
      grp.update(f.ctrl, false)
    end
  end
end


grp.update(USING_POWER_GA, using_power)


-- ============================ ДИАГНОСТИКА ===================================
-- Диагностика делается максимально "читаемой глазами".
-- Если часть объектов диагностики не существует - LM просто не обновит их.

-- DIAG_MODE_OBJ:
--  zigbee = количество зон, управляемых по данным Zigbee (воздух),
--  fallback = количество зон, управляемых по полу (Zigbee недоступен),
--  on = количество зон, у которых реле тёплых полов включено сейчас

-- DIAG_BLOCK_OBJ:
--  overheat = количество зон, заблокированных защитой по перегреву пола,
--  long_block = количество зон, заблокированных из-за слишком долгой работы без свежего Zigbee

-- DIAG_WEATHER_OBJ:
--  Tout = текущая наружная температура,
--  kw_base = базовая погодная добавка к уставкам (без учета коэффициентов комнат)

-- DIAG_POWER_OBJ:
--  using = суммарная мощность включённых тёплых полов (Вт),
--  limit = общий лимит доступной мощности (Вт)



-- Короткие строки
grp.update(DIAG_MODE_OBJ, string.format('zigbee=%d fallback=%d on=%d', cnt_zigbee, cnt_fallback, cnt_on))
grp.update(DIAG_BLOCK_OBJ, string.format('overheat=%d long_block=%d', cnt_overheat, cnt_longblock))
grp.update(DIAG_WEATHER_OBJ, string.format('Tout=%s kw_base=%s', fmt1(to_number(tout)), fmt1(kw_base)))
grp.update(DIAG_POWER_OBJ, string.format('using=%d limit=%d', using_power, grp.getvalue(MAX_POWER_GA)))

-- Один "жирный" текстовый статус
local text = ''
text = text .. 'ТП авто: ВКЛ\n'
text = text .. 'Температура улицы: ' .. fmt1(to_number(tout)) .. '°C\n'
text = text .. 'Погодная добавка база: ' .. fmt1(kw_base) .. '°C\n'
text = text .. 'Режимы: zigbee=' .. cnt_zigbee .. ', fallback=' .. cnt_fallback .. '\n'
text = text .. 'Блокировки: overheat=' .. cnt_overheat .. ', long_block=' .. cnt_longblock .. '\n'
text = text .. 'Мощность: ' .. using_power .. ' / ' .. grp.getvalue(MAX_POWER_GA) .. ' Вт\n'

grp.update(DIAG_TEXT_OBJ, text)