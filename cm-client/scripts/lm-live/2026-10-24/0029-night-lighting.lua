latitude = 56.02
longitude = 38.21

ts, tms = os.microtime()
sunrise, sunset = rscalc(latitude, longitude)

sunrise_hour = math.floor(sunrise / 60)
sunrise_minute = sunrise % 60

sunset_hour = math.floor(sunset / 60)
sunset_minute = sunset % 60

sunrise_text = string.format('%02d:%02d', sunrise_hour, sunrise_minute)
sunset_text = string.format('%02d:%02d', sunset_hour, sunset_minute)


now = os.date('*t')

now_min = now.hour * 60 + now.min

outside_lights = grp.tag({'outside', 'light','control'}, 'all')

if math.abs(now_min - sunrise) < 1 then
    outside_lights:update(false,1)
    log('sunrise timer run ' .. sunrise_text .. '/' .. sunset_text .. ': ' .. os.udifftime(ts, tms))
end

if math.abs(now_min - sunset) < 1  then
    outside_lights:update(true,1)
    log('sunset timer run ' .. sunrise_text .. '/' .. sunset_text .. ': ' .. os.udifftime(ts, tms))
end