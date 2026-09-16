require('json')
--[[
function OnOff2Bool(s)
    if string.upper(s) == 'ON' then
        --log('OnOff2Bool returned true')
        return true
    end
    
    if string.upper(s) == 'OFF' then
        --log('OnOff2Bool returned false')
        return false
    end    
end
--]]

function OnOff2Bool(s)
    return s == "ON"
end

local AI_SRV_MIN_INTERVAL = 15
local ai_last = {}

-- Zigbee JSON always grp.update: humidity/battery publishes include the same
-- temperature, and checkupdate/float-compare leaves temperature.updatetime stale.
-- AI-SRV still goes through ai_knx (15s / skip unchanged) before this.
local function knx_check(ga, value)
  grp.update(ga, value)
end

-- force=true: availability / offline, skip interval.
local function ai_knx(ga, value, force)
  local now = os.time()
  local prev = ai_last[ga]
  if not force then
    if prev and prev.v == value then
      return
    end
    if prev and (now - prev.t) < AI_SRV_MIN_INTERVAL then
      return
    end
  end
  ai_last[ga] = { v = value, t = now }
  knx_check(ga, value)
end

local function ai_num(v, status)
  if status ~= nil and status ~= 'fresh' then return -1 end
  if v == nil then return -1 end
  if type(v) ~= 'number' then return -1 end
  return v
end

local function ai_mib_gib(v, status)
  local n = ai_num(v, status)
  if n < 0 then return -1 end
  return n / 1024
end

local function ai_bytes_gib(v, status)
  local n = ai_num(v, status)
  if n < 0 then return -1 end
  return n / 1073741824
end

local function apply_ai_srv_offline_numerics()
  local gas = {
    '35/1/2','35/1/3','35/1/4','35/1/7','35/1/8',
    '35/1/9','35/1/10','35/1/11','35/1/12','35/1/13','35/1/18',
  }
  for i = 1, #gas do
    ai_knx(gas[i], -1, true)
  end
end

local function apply_ai_srv_json(dd)
  if not dd then
    apply_ai_srv_offline_numerics()
    return
  end
  ai_knx('35/1/2', ai_num(dd.temperature, dd.temperature_status))
  ai_knx('35/1/3', ai_num(dd.rpm, dd.rpm_status))
  ai_knx('35/1/4', ai_num(dd.pwm, nil))
  if dd.serial_state == nil or dd.serial_state == '' then
    ai_knx('35/1/5', 'unknown')
  else
    ai_knx('35/1/5', dd.serial_state)
  end
  if dd.protection_state == nil or dd.protection_state == '' then
    ai_knx('35/1/6', 'unknown')
  else
    ai_knx('35/1/6', dd.protection_state)
  end
  if dd.sensor_loss_elapsed_seconds == nil then
    ai_knx('35/1/7', 0)
  else
    ai_knx('35/1/7', ai_num(dd.sensor_loss_elapsed_seconds, nil))
  end
  ai_knx('35/1/8', ai_num(dd.gpu_utilization_percent, dd.gpu_utilization_percent_status))
  ai_knx('35/1/9', ai_mib_gib(dd.gpu_memory_used_mib, dd.gpu_memory_used_mib_status))
  ai_knx('35/1/10', ai_num(dd.gpu_power_draw_w, dd.gpu_power_draw_w_status))
  ai_knx('35/1/11', ai_num(dd.cpu_utilization_percent, dd.cpu_utilization_percent_status))
  ai_knx('35/1/12', ai_bytes_gib(dd.ram_used_bytes, dd.ram_used_bytes_status))
  ai_knx('35/1/13', ai_num(dd.disk_used_percent, dd.disk_used_percent_status))
  if dd.boot_id == nil or dd.boot_id == '' then
    ai_knx('35/1/14', 'unknown')
  else
    ai_knx('35/1/14', dd.boot_id)
  end
  local rs = dd.last_shutdown_reason
  if type(rs) ~= 'table' then
    ai_knx('35/1/15', 'none')
    ai_knx('35/1/16', 'none')
    ai_knx('35/1/17', 'none')
    ai_knx('35/1/18', -1)
    ai_knx('35/1/19', 'none')
  else
    ai_knx('35/1/15', rs.reason or 'none')
    ai_knx('35/1/16', rs.event_id or 'none')
    ai_knx('35/1/17', rs.status or 'none')
    ai_knx('35/1/18', ai_num(rs.last_temperature_c, nil))
    ai_knx('35/1/19', rs.timestamp_utc or 'none')
  end
end

if not mclient then
    -- control, topic -> address map
    controlmap = {
    --    ['RELAY_25/DRM88ER_25/ADR:34/IR21'] = '1/2/15',
   --     ['RELAY_25/DRM88ER_25/ADR:34/IR22'] = '1/1/6',
   --     ['RELAY_25/DRM88ER_25/ADR:34/IR23'] = '1/1/5',
    --    ['RELAY_25/DRM88ER_25/ADR:25/IR24'] = '32/1/44',
    --    ['RELAY_25/DRM88ER_25/ADR:34/IR25'] = '1/1/12'
    }
    
    statusmap = {
       	--[[ чтение статусов светильников
        ['RELAY_23/DRM88ER_23/ADR:23/COIL1'] = '1/2/1',
		['RELAY_23/DRM88ER_23/ADR:23/COIL2'] = '1/2/2',
        ['RELAY_23/DRM88ER_23/ADR:23/COIL3'] = '1/2/3',
        ['RELAY_23/DRM88ER_23/ADR:23/COIL4'] = '1/2/4',
        ['RELAY_23/DRM88ER_23/ADR:23/COIL5'] = '1/2/5',
        ['RELAY_23/DRM88ER_23/ADR:23/COIL6'] = '1/2/6',
        ['RELAY_23/DRM88ER_23/ADR:23/COIL7'] = '1/2/7',
        ['RELAY_23/DRM88ER_23/ADR:23/COIL8'] = '1/2/8',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL1'] = '1/2/9',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL2'] = '1/2/10',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL3'] = '1/2/11',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL4'] = '1/2/12',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL5'] = '1/2/13',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL6'] = '1/2/14',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL7'] = '1/2/15',
        ['RELAY_24/DRM88ER_24/ADR:24/COIL8'] = '1/2/16',
        --]] 
         
        -- свет на чердаке (на 22 контроллере другие правила наименования топиков, обратить внимание!)
        ['RELAY_22/DRM88ER_22/COIL2'] = '1/2/17',
          
        -- свет торшера в гостиной через zigbee
        ['zigbee2mqtt/FloorLamp_switcher'] = {state = {addr = '1/2/18', convert_func = OnOff2Bool }},
        
        ['zigbee2mqtt/PIR_sensor'] = {occupancy = "32/7/13", illuminance = "32/7/14", battery = "32/7/15",  linkquality = "32/7/16",illuminance_interval = "32/7/17", keep_time = "32/7/18"},
        ['zigbee2mqtt/Backlight_kitchen_table'] = {state = {addr = '1/2/19', convert_func = OnOff2Bool }},
        ['zigbee2mqtt/T-Lamp'] = {state = {addr = '1/2/20', convert_func = OnOff2Bool }},
        ['zigbee2mqtt/Movie_Projector'] = {state = {addr = '32/6/3', convert_func = OnOff2Bool }},
        
        ['zigbee2mqtt/sensor_1_temp_hum_server_room_fl1'] = {temperature = "33/1/1", humidity = "33/1/2", battery = "33/1/3"},
        ['zigbee2mqtt/sensor_2_temp_hum_bedroom_fl1'] = {temperature = "33/1/4", humidity = "33/1/5", battery = "33/1/6"},
        ['zigbee2mqtt/sensor_3_temp_hum_living_room_fl1'] = {temperature = "33/1/7", humidity = "33/1/8", battery = "33/1/9"},
        ['zigbee2mqtt/sensor_4_temp_hum_bathroom_fl1'] = {temperature = "33/1/10", humidity = "33/1/11", battery = "33/1/12"},
        ['zigbee2mqtt/sensor_5_temp_hum_kitchen_fl1'] = {temperature = "33/1/13", humidity = "33/1/14", battery = "33/1/15"},
        ['zigbee2mqtt/sensor_6_temp_hum_office_fl2'] = {temperature = "33/1/16", humidity = "33/1/17", battery = "33/1/18"},
        ['zigbee2mqtt/sensor_7_temp_hum_tima_bedroom_fl2'] = {temperature = "33/1/19", humidity = "33/1/20", battery = "33/1/21"},
        ['zigbee2mqtt/sensor_8_temp_hum_nastya_bedroom_fl2'] = {temperature = "33/1/22", humidity = "33/1/23", battery = "33/1/24"},
        ['zigbee2mqtt/sensor_9_temp_hum_hall_fl2'] = {temperature = "33/1/25", humidity = "33/1/26", battery = "33/1/27"},
        ['zigbee2mqtt/sensor_10_temp_hum_hall_fl1'] = {temperature = "33/1/28", humidity = "33/1/29", battery = "33/1/30"},
        ['zigbee2mqtt/sensor_11_temp_hum_bathroom_fl2'] = {temperature = "33/1/31", humidity = "33/1/32", battery = "33/1/33"},
        ['zigbee2mqtt/sensor_12_temp_hum_bedroom_fl2'] = {temperature = "33/1/34", humidity = "33/1/35", battery = "33/1/36"},
        ['ble-mqtt-bridge/RK-M173S'] = {temperature = "33/1/37", state = {addr = '33/1/38', convert_func = OnOff2Bool } },
        ['cooler-arduino/alex-neuro'] = 'ai_srv_json',
        ['cooler-arduino/alex-neuro/availability'] = 'ai_srv_avail',
        --[[
        ['zigbee2mqtt/TempHum_sensor_living_room'] = {temperature = "32/7/1", humidity = "32/7/2", battery = "32/7/3",  linkquality = "32/7/4"},
        ['zigbee2mqtt/TempHum_sensor_office'] = {temperature = "32/7/5", humidity = "32/7/6", battery = "32/7/7",  linkquality = "32/7/8"},
        ['zigbee2mqtt/TempHum_sensor_bathroom1'] = {temperature = "32/7/9", humidity = "32/7/10", battery = "32/7/11",  linkquality = "32/7/12"},
        --]]
        
        
    }
    
    
    
    host = "127.0.0.1"
    port = 1883 
    username = "user"
    password = "password"
    connected = false
    
    mclient = require("mosquitto").new()
    
    mclient.ON_CONNECT = function(status, rc, msg)
	    connected = status
    	if status then
            
            for topic, _ in pairs(statusmap) do
    			mclient:subscribe(topic)
    		end                        

        else
            mclient:disconnect()
            log("mclient.ON_CONNECT - disconnect")
    	end
    end
    
    mclient.ON_DISCONNECT = function(status, rc, msg)
        log("mclient.ON_DISCONNECT",status, rc, msg)
        if connected then
            log("reconnect to mqtt brocker",mclient:reconnect())
        end
    end
    
    mclient.ON_MESSAGE = function(mid, topic, data)
        if topic == 'cooler-arduino/alex-neuro/availability' then
          local online = (data == 'online')
          ai_knx('35/1/1', online, true)
          if not online then apply_ai_srv_offline_numerics() end
          return
        end
        if topic == 'cooler-arduino/alex-neuro' then
          apply_ai_srv_json(json.pdecode(data))
          return
        end

        -- находим соответствующий объект с адресом по топику
        local obj = statusmap[ topic ]
        -- если нашли
        if obj then
            -- и этот объекта таблица (то есть содержит поля) - это данные формате json которые присылают zigbee устройства
            if type(obj) == "table" then
                -- декодируем данные из формата json
                dd = json.pdecode(data)
                --log(dd)
                
                -- есди данные содержаться в формате json  и их удалось декодировать
                if dd then
                    -- выбираем из полученного массива название поля и его значение
                    for field, v in pairs(dd) do
                        -- ищем поле с таким же названием в объекте и получаем его адресс
                        local address = obj[field]
                        -- если нашли
                        if address then
                            if type(address) == "table" then
                                -- если объект таблица, то значит содержит функцию конвертирования значения
                                knx_check(address.addr, address.convert_func(v))
                            else
                                -- если объекта содержит только адрес, то по нему устанавливаем значение из поля json без конвертации
                                knx_check(address, v)
                            end    

                        end
                    end
                end    
                
            else   
                -- сырые данные в виде строки от контроллеров Разумного Дома
                local value = data or 0
                if value ~= nil then
                    --log("reciveded value: "..topic.. ":" .. value )
                    grp.checkupdate(obj, value)
                end
                
            end    
        end
        
    end
    
    
    mclient.ON_LOG = function(level, msg)
       -- log("loging from broker",level, msg )       
    end
    
    function mconnect()
        
        mclient:login_set(username, password)
        local status, rc, msg = mclient:connect(host, port)
        --log("mconnect()",status, rc, msg)
        
        if not status then
        	log('mqtt connect failed ' .. tostring(msg))
            connected = false
            mclient = nil
        else
            log("connect is successful")
            mclient:loop_forever()
        end
      
    end
    
    mconnect()
    
end
--os.sleep(0.5)



