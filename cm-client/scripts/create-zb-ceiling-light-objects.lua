-- One-shot. Scripting → User / Event. Not resident.
-- Creates 18 virtual GAs 34/1|2/1–9 for Zigbee ceiling brightness/CCT/RGB.
-- Skip existing addresses. Then try tag relays 1/1/13, 1/1/14, 1/1/15 with zb_light_sync.
-- Catalog: cm-client/scripts/zb_ceiling_light_catalog.json

local COMMENT = 'source: zb_ceiling_light_catalog'
local RELAY_TAG = 'zb_light_sync'
local RELAYS = { '1/1/13', '1/1/14', '1/1/15' }

local TAGS_CONTROL = { '2floor', 'light', 'zigbee', 'zigbee_send' }
local TAGS_STATUS = { '2floor', 'light', 'zigbee', 'status' }

local objects = {
  { address = '34/1/1', name = 'Свет Zigbee - Тима - яркость',         datatype = 5,  tags = TAGS_CONTROL },
  { address = '34/2/1', name = 'Свет Zigbee - Тима - яркость:status',  datatype = 5,  tags = TAGS_STATUS },
  { address = '34/1/2', name = 'Свет Zigbee - Тима - CCT',             datatype = 9,  tags = TAGS_CONTROL },
  { address = '34/2/2', name = 'Свет Zigbee - Тима - CCT:status',      datatype = 9,  tags = TAGS_STATUS },
  { address = '34/1/3', name = 'Свет Zigbee - Тима - RGB',             datatype = 12, tags = TAGS_CONTROL },
  { address = '34/2/3', name = 'Свет Zigbee - Тима - RGB:status',      datatype = 12, tags = TAGS_STATUS },
  { address = '34/1/4', name = 'Свет Zigbee - Холл - яркость',         datatype = 5,  tags = TAGS_CONTROL },
  { address = '34/2/4', name = 'Свет Zigbee - Холл - яркость:status',  datatype = 5,  tags = TAGS_STATUS },
  { address = '34/1/5', name = 'Свет Zigbee - Холл - CCT',             datatype = 9,  tags = TAGS_CONTROL },
  { address = '34/2/5', name = 'Свет Zigbee - Холл - CCT:status',      datatype = 9,  tags = TAGS_STATUS },
  { address = '34/1/6', name = 'Свет Zigbee - Холл - RGB',             datatype = 12, tags = TAGS_CONTROL },
  { address = '34/2/6', name = 'Свет Zigbee - Холл - RGB:status',      datatype = 12, tags = TAGS_STATUS },
  { address = '34/1/7', name = 'Свет Zigbee - Кабинет - яркость',      datatype = 5,  tags = TAGS_CONTROL },
  { address = '34/2/7', name = 'Свет Zigbee - Кабинет - яркость:status', datatype = 5,  tags = TAGS_STATUS },
  { address = '34/1/8', name = 'Свет Zigbee - Кабинет - CCT',          datatype = 9,  tags = TAGS_CONTROL },
  { address = '34/2/8', name = 'Свет Zigbee - Кабинет - CCT:status',   datatype = 9,  tags = TAGS_STATUS },
  { address = '34/1/9', name = 'Свет Zigbee - Кабинет - RGB',          datatype = 12, tags = TAGS_CONTROL },
  { address = '34/2/9', name = 'Свет Zigbee - Кабинет - RGB:status',   datatype = 12, tags = TAGS_STATUS },
}

local function exists(addr)
  local ok, val = pcall(function() return grp.find(addr) end)
  if ok and val then return true end
  for _, obj in ipairs(grp.all() or {}) do
    if obj.address == addr then return true end
  end
  return false
end

local function tag_list(obj)
  local tags = obj and obj.tags
  local out = {}
  if type(tags) == 'string' then
    for t in string.gmatch(tags, '[^,%s]+') do
      out[#out + 1] = t
    end
  elseif type(tags) == 'table' then
    for k, v in pairs(tags) do
      if type(v) == 'string' then
        out[#out + 1] = v
      elseif type(k) == 'string' and (v == true or v == 1) then
        out[#out + 1] = k
      end
    end
  end
  return out
end

local function has_tag(obj, tag)
  for _, t in ipairs(tag_list(obj)) do
    if t == tag then return true end
  end
  return false
end

local function find_obj(addr)
  local ok, val = pcall(function() return grp.find(addr) end)
  if ok and val then return val end
  for _, obj in ipairs(grp.all() or {}) do
    if obj.address == addr then return obj end
  end
  return nil
end

-- Best-effort: grp.addtags / grp.tags setter. If the firmware has neither, add zb_light_sync in LM UI.
local function ensure_relay_tag(addr, tag)
  local obj = find_obj(addr)
  if not obj then
    log('create-zb-ceiling: relay ' .. addr .. ' not found, skip tag ' .. tag)
    return
  end
  if has_tag(obj, tag) then
    log('create-zb-ceiling: tag already on ' .. addr)
    return
  end

  local merged = tag_list(obj)
  merged[#merged + 1] = tag

  if type(grp.addtags) == 'function' then
    local ok = pcall(function() grp.addtags(addr, { tag }) end)
    if ok then
      log('create-zb-ceiling: tagged ' .. addr .. ' ' .. tag .. ' via grp.addtags')
      return
    end
  end

  if type(grp.tags) == 'function' then
    local ok = pcall(function() grp.tags(addr, merged) end)
    if ok then
      log('create-zb-ceiling: tagged ' .. addr .. ' ' .. tag .. ' via grp.tags')
      return
    end
  end

  if type(obj.addtags) == 'function' then
    local ok = pcall(function() obj:addtags({ tag }) end)
    if ok then
      log('create-zb-ceiling: tagged ' .. addr .. ' ' .. tag .. ' via obj:addtags')
      return
    end
  end

  log('create-zb-ceiling: cannot add tag ' .. tag .. ' to ' .. addr .. ' via API; add in LM UI')
end

for _, o in ipairs(objects) do
  if exists(o.address) then
    log('create-zb-ceiling: skip ' .. o.address)
  else
    grp.create({
      address = o.address,
      name = o.name,
      datatype = o.datatype,
      tags = o.tags,
      comment = COMMENT,
    })
    log('create-zb-ceiling: created ' .. o.address .. ' ' .. o.name)
  end
end

for _, addr in ipairs(RELAYS) do
  ensure_relay_tag(addr, RELAY_TAG)
end
