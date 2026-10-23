-- Скрипт для LogicMachine:
-- Расчитывает потребление за последний полный час и последние сутки,
-- используя накопительный счётчик энергии (KNX-объект "32/1/39").
-- Результаты отправляются в KNX-объекты "32/1/57" (час) и "32/1/58" (сутки).

-- Получаем текущее значение счётчика
local currentEnergy = grp.getvalue("32/1/39")
if currentEnergy == nil then
  -- Если значение не получено, прекращаем выполнение
  return
end

-- Текущее время
local now = os.time()
local nowTable = os.date("*t", now)

-- Определяем начало текущего часа (граница часа)
local currentHourBoundary = now - (nowTable.min * 60 + nowTable.sec)
-- Определяем начало текущего дня (граница суток)
local currentDayBoundary = now - (nowTable.hour * 3600 + nowTable.min * 60 + nowTable.sec)

-- Извлекаем сохранённые границы и показания
local lastHourBoundary = storage.get("lastHourBoundary")
local lastHourEnergy    = storage.get("lastHourEnergy")
local lastDayBoundary   = storage.get("lastDayBoundary")
local lastDayEnergy     = storage.get("lastDayEnergy")

-- Если данных ещё нет (первый запуск) – инициализируем их текущими значениями
if lastHourBoundary == nil or lastHourEnergy == nil then
  storage.set("lastHourBoundary", currentHourBoundary)
  storage.set("lastHourEnergy", currentEnergy)
  lastHourBoundary = currentHourBoundary
  lastHourEnergy = currentEnergy
end

if lastDayBoundary == nil or lastDayEnergy == nil then
  storage.set("lastDayBoundary", currentDayBoundary)
  storage.set("lastDayEnergy", currentEnergy)
  lastDayBoundary = currentDayBoundary
  lastDayEnergy = currentEnergy
end

----------------------------------------------------
-- Расчёт потребления за последний полный час
----------------------------------------------------
local gapHour = currentHourBoundary - lastHourBoundary
if gapHour >= 3600 then
  if gapHour == 3600 then
    -- Нормальный случай: ровно один час прошёл
    local consumptionHour = currentEnergy - lastHourEnergy
    grp.checkupdate("32/1/57", consumptionHour, 0)
  else
    -- Если прошло более одного часа, значит контроллер был выключен или скрипт не запускался.
    -- Чтобы не передавать завышенное значение (которое охватывает несколько часов),
    -- здесь можно либо вычислить среднее, либо пропустить обновление.
    -- В данном примере обновление не производится.
  end
  -- Обновляем сохранённые данные для часа
  storage.set("lastHourBoundary", currentHourBoundary)
  storage.set("lastHourEnergy", currentEnergy)
end

----------------------------------------------------
-- Расчёт потребления за последние сутки
----------------------------------------------------
local gapDay = currentDayBoundary - lastDayBoundary
if gapDay >= 86400 then
  if gapDay == 86400 then
    -- Ровно одни сутки прошли
    local consumptionDay = currentEnergy - lastDayEnergy
    grp.checkupdate("32/1/58", consumptionDay, 0)
  else
    -- Если прошло более суток, то данные охватывают несколько дней.
    -- Чтобы не передавать некорректное значение (слишком большое),
    -- обновление не производится.
    -- При необходимости можно вычислить среднее дневное потребление:
    -- local daysPassed = gapDay / 86400
    -- local consumptionDay = (currentEnergy - lastDayEnergy) / daysPassed
  end
  -- Обновляем сохранённые данные для суток
  storage.set("lastDayBoundary", currentDayBoundary)
  storage.set("lastDayEnergy", currentEnergy)
end