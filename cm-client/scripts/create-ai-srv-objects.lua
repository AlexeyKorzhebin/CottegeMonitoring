-- One-shot. Scripting → User / Event. Not resident.
-- Tags monitoring,gpu,ai-srv. Skip existing addresses.

local TAGS = { 'monitoring', 'gpu', 'ai-srv' }
local COMMENT = 'source: cooler-arduino/alex-neuro'

local objects = {
  { address = '35/1/1',  name = 'AI-SRV - online',              datatype = 1 },
  { address = '35/1/2',  name = 'AI-SRV - температура',         datatype = 9 },
  { address = '35/1/3',  name = 'AI-SRV - RPM',                 datatype = 9 },
  { address = '35/1/4',  name = 'AI-SRV - PWM',                 datatype = 9 },
  { address = '35/1/5',  name = 'AI-SRV - serial',              datatype = 255 },
  { address = '35/1/6',  name = 'AI-SRV - защита',              datatype = 255 },
  { address = '35/1/7',  name = 'AI-SRV - потеря датчика с',    datatype = 9 },
  { address = '35/1/8',  name = 'AI-SRV - GPU %',               datatype = 9 },
  { address = '35/1/9',  name = 'AI-SRV - VRAM GiB',            datatype = 9 },
  { address = '35/1/10', name = 'AI-SRV - мощность Вт',         datatype = 9 },
  { address = '35/1/11', name = 'AI-SRV - CPU %',               datatype = 9 },
  { address = '35/1/12', name = 'AI-SRV - RAM GiB',             datatype = 9 },
  { address = '35/1/13', name = 'AI-SRV - диск %',              datatype = 9 },
  { address = '35/1/14', name = 'AI-SRV - boot id',             datatype = 255 },
  { address = '35/1/15', name = 'AI-SRV - авария причина',      datatype = 255 },
  { address = '35/1/16', name = 'AI-SRV - авария id',           datatype = 255 },
  { address = '35/1/17', name = 'AI-SRV - авария статус',       datatype = 255 },
  { address = '35/1/18', name = 'AI-SRV - авария температура',  datatype = 9 },
  { address = '35/1/19', name = 'AI-SRV - авария время',        datatype = 255 },
}

local function exists(addr)
  local ok, val = pcall(function() return grp.find(addr) end)
  if ok and val then return true end
  for _, obj in ipairs(grp.all() or {}) do
    if obj.address == addr then return true end
  end
  return false
end

for _, o in ipairs(objects) do
  if exists(o.address) then
    log('create-ai-srv: skip ' .. o.address)
  else
    grp.create({
      address = o.address,
      name = o.name,
      datatype = o.datatype,
      tags = TAGS,
      comment = COMMENT,
    })
    log('create-ai-srv: created ' .. o.address .. ' ' .. o.name)
  end
end
