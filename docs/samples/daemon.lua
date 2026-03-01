require("apps")
require('json')
require('encdec')  







-----------------------------------------------------------------


HDL = {
	-- destination ip
	dstip = '192.168.1.120',
	-- packet constant data
	magic = 'HDLMIRACLE',
	-- leading code
	lcode = string.char(0xAA, 0xAA),
	-- source device settings
	srcsubnet = 1,
	srcdevice = 210,
	devicetype = 0xFFFE,
	-- command types
	cmd = {
		scene = 0x0002, -- scene select
		scenereply = 0x0003, -- scene select answerback
		sequence = 0x001A, -- sequence select
		sequencereply = 0x001B, -- sequence select answerback
		chanreg = 0x0031, -- single channel regulate
		chanregreply = 0x0032, -- single channel regulate answerback
		chanstat = 0x0033, -- read status of single channel targets
		chanstatreply = 0x0034, -- single channel targets status answerback
		universalswitch = 0xE01C,
		universalswitchreply = 0xE01D
	}
}
 
knxtohdl =  {}  --loadmapping('/home/ftp/knx2hdl.json')
hdltoknx =  {} -- loadmapping('/home/ftp/hdl2knx.json')



hdltoknx[1] = {hdl_net = 1, hdl_dev = 210, type = HDL.cmd.chanreg, channel = 1, knx_obj = '13/1/1'}
hdltoknx[2] = {hdl_net = 1, hdl_dev = 210, type = HDL.cmd.chanreg, channel = 2, knx_obj = '13/1/2'}
hdltoknx[3] = {hdl_net = 1, hdl_dev = 210, type = HDL.cmd.scene, 	area = 1, scene = 1, knx_obj = '13/1/3'}
hdltoknx[4] = {hdl_net = 1, hdl_dev = 210, type = HDL.cmd.sequence, area = 1, seq = 1, knx_obj = '13/1/4'}
hdltoknx[5] = {hdl_net = 1, hdl_dev = 212, type = HDL.cmd.universalswitch, channel = 4, knx_obj = '13/1/5'}


-- только scale или 1 байт
knxtohdl[1] = {knx_obj = 'KNX2HDL_chanreg1', hdl_net = 1, hdl_dev = 210, type = HDL.cmd.chanreg, channel = 1, delay = 1}
knxtohdl[2] = {knx_obj = 'KNX2HDL_chanreg2', knx_status = 'KNX2HDL_chanreg2_st', hdl_net = 1, hdl_dev = 210, type = HDL.cmd.chanreg, channel = 2}
-- номер scene передается как значение knx объекта
knxtohdl[3] = {knx_obj = 'KNX2HDL_scene1', hdl_net = 1, hdl_dev = 210, type = HDL.cmd.scene, area = 1}
knxtohdl[4] = {knx_obj = 'KNX2HDL_scene2', hdl_net = 1, hdl_dev = 210, type = HDL.cmd.scene, area = 1}
knxtohdl[5] = {knx_obj = 'KNX2HDL_seq', hdl_net = 1, hdl_dev = 210, type = HDL.cmd.sequence, seq = 2, area = 1}
knxtohdl[6] = {knx_obj = 'KNX2HDL_UV', hdl_net = 1, hdl_dev = 210, type = HDL.cmd.universalswitch, channel = 4}




--log('knxtohdl',knxtohdl)
--log('hdltoknx',hdltoknx)



HDL.init = function()

	require('socket')
	
	local ip, chunk, chunks, data
	-- read interface data
	vv = io.readproc('if-json')
	data = json.pdecode(vv)
	
	
	if not data or not data.eth0 then
	error('cannot get interface data')
	end
	
	-- ip header
	HDL.iphdr = ''
	-- broadcast address
	HDL.bcast = data.eth0.bcast
	-- source ip
	HDL.srcip = data.eth0.inetaddr
	
	-- split ip address into chunks
	chunks = HDL.srcip:split('.')
	
	-- add ip address chunks
	for i = 1, 4 do
		chunk = tonumber(chunks[ i ])
		HDL.iphdr = HDL.iphdr .. string.char(chunk)
		end
end
 
HDL.decode = function(packet)
	local len, data, src, crc
	
	-- primary header
	if packet:sub(5, 14) ~= HDL.magic then
	return nil, 'magic'
	end
	
	-- leading code
	if packet:sub(15, 16) ~= HDL.lcode then
		return nil, 'lcode'
	end
	
	-- get data length and check against
	len = packet:byte(17)
	if len and len + 16 ~= packet:len() then
		return nil, 'len'
	end
	
	-- get packet data and check crc
	data = packet:sub(17, len + 14)
	crc = packet:byte(len + 15) * 0x100 + packet:byte(len + 16)
	
	if encdec.crc16(data) ~= crc then
		return nil, 'crc'
	end
	
	-- return parsed packet
	return {
		srcip = string.format('%d.%d.%d.%d', packet:byte(1, 4)),
		srcsubnet = packet:byte(18),
		srcdevice = packet:byte(19),
		devicetype = (packet:byte(20) * 0x100 + packet:byte(21)),
		opcode = (packet:byte(22) * 0x100 + packet:byte(23)),
		dstsubnet = packet:byte(24),
		dstdevice = packet:byte(25),
		additional = packet:sub(26, len + 14)
	}
end
 
HDL.word = function(v)
	return string.char(bit.band(bit.rshift(v, 8), 0xFF), bit.band(v, 0xFF))
end
 


HDL.encode = function(cmd, dstsubnet, dstdevice, extra)
	local packet, len, crc, data
	
    log('encode',cmd, dstsubnet, dstdevice, extra)
    
	-- perform init if required
	if not HDL.iphdr then
		HDL.init()
	end
	
	-- start packet: ip, magic and leading code
	packet = { HDL.iphdr, HDL.magic, HDL.lcode }
	-- base data
	data = string.char(HDL.srcsubnet, HDL.srcdevice) .. 
	HDL.word(HDL.devicetype) .. HDL.word(cmd) .. string.char(dstsubnet, dstdevice)
	
	-- add extra data parameters
	if type(extra) == 'string' then
		data = data .. extra
	end
	
	-- calculate length and crc
	len = string.char(data:len() + 3)
	crc = encdec.crc16(len .. data)
	
	table.insert(packet, len)
	table.insert(packet, data)
	table.insert(packet, HDL.word(crc))
	
	
	return table.concat(packet)
end
 
HDL.send = function(packet)
	local client = socket.udp()
	client:sendto(packet, HDL.dstip, 6000)
end
 
HDL.sendcmd = function(cmd, dstsubnet, dstdevice, a, b, c)
	local extra, packet

	extra = string.char(a, b) .. HDL.word(c or 0)
	packet = HDL.encode(cmd, dstsubnet, dstdevice, extra)

	HDL.send(packet)
end




 
HDL.chanreg = function(dstsubnet, dstdevice, chan, value, delay)
	if type(value) == 'boolean' then
		value = value and 100 or 0
	end

	HDL.sendcmd(HDL.cmd.chanreg, dstsubnet, dstdevice, chan, value, delay)
end
 
HDL.sequence = function(dstsubnet, dstdevice, area, value)
	HDL.sendcmd(HDL.cmd.sequence, dstsubnet, dstdevice, area, value)
end
 
HDL.scene = function(dstsubnet, dstdevice, area, scene)
	HDL.sendcmd(HDL.cmd.scene, dstsubnet, dstdevice, area, scene)
end

HDL.universal_switch = function(dstsubnet, dstdevice, id, value)
	HDL.sendcmd(HDL.cmd.universalswitch, dstsubnet, dstdevice, id, value)
end


HDL.chanregreply = function(chan, value)
	local extra, packet
	
	extra = string.char(chan, 0xF8, value, chan) 
	packet = HDL.encode(HDL.cmd.chanregreply, 255, 255, extra)
	HDL.send(packet)
end

HDL.scenereply = function(area, scene)
	local extra, packet
	
    log('scenereply',area, scene)
    
	extra = string.char(area, scene, 1,1) 
	packet = HDL.encode(HDL.cmd.scenereply, 255, 255, extra)
	HDL.send(packet)
end

HDL.sequencereply = function(area, seq)
	local extra, packet
	
    log('sequencereply',area, seq)  
    
	extra = string.char(area, seq) 
	packet = HDL.encode(HDL.cmd.sequencereply, 255, 255, extra)
	HDL.send(packet)
end

HDL.universalswitchreply = function(id, value)
	local extra, packet
	
    if value > 0 then value = 1 end
    
    log('universalswitchreply into', id,value)
    
	extra = string.char(id, value) 
	packet = HDL.encode(HDL.cmd.universalswitchreply, 255, 255, extra)
	HDL.send(packet)
end




  -- knx group write handler

function convert_to_uint8(event)
	local obj = grp.find(event.dstraw)
    local value = nil
	if obj then
        if obj.datatype == dt.bool or obj.datatype == dt.boolean or obj.datatype == dt.switch then
            local res = knxdatatype.decode(event.datahex, dt.bool)
            if res then value = 100 else  value = 0 end
		else
	    	value = knxdatatype.decode(event.datahex, dt.scale)
		end  		
	
    end

    return value
		
end

function knxgroupwrite(event)
  	
   -- check if address is mapped
    for index, rec in ipairs(knxtohdl) do
        
        if event.dst == rec.knx_obj or event.dst == grp.alias(rec.knx_obj) then
            log('knxgroupwrite', rec.knx_obj, rec.type, event.datahex)
            
            if rec.type == HDL.cmd.chanreg then
                value = convert_to_uint8(event)
                log('chanreg',rec.hdl_net, rec.hdl_dev, rec.channel, value, rec.delay or 0)
                
                HDL.chanreg(rec.hdl_net, rec.hdl_dev, rec.channel, value, rec.delay or 0)
                return
            elseif rec.type == HDL.cmd.scene then
                value = knxdatatype.decode(event.datahex, dt.scale)
                
                log('scene',rec.hdl_net, rec.hdl_dev, rec.area, value)
                HDL.scene(rec.hdl_net, rec.hdl_dev,rec.area,value)
                return
            elseif rec.type == HDL.cmd.sequence then
                log('sequence',rec.hdl_net, rec.hdl_dev, rec.area)
                HDL.sequence(rec.hdl_net, rec.hdl_dev,rec.area,1)
                return
       		elseif rec.type == HDL.cmd.universalswitch then
                value = convert_to_uint8(event)
               	if value > 0 then res = 1 else res = 0 end
                
                log('universalswitch',rec.hdl_net, rec.hdl_dev, rec.channel, value, rec.delay)

                HDL.universal_switch(rec.hdl_net, rec.hdl_dev, rec.channel,res)
                return
            end
        end
	end

    
end



function parse(packet)
    log('parse')
    
    if packet.opcode == HDL.cmd.chanreg then
        channel = packet.additional:byte(1)
		value = packet.additional:byte(2)
	
        log('chanreg')
        
    	for index, rec in ipairs(hdltoknx) do
            if packet.dstsubnet == rec.hdl_net and packet.dstdevice == rec.hdl_dev and channel == rec.channel and packet.opcode == rec.type  then
                log('chanreg found', rec, value)
                grp.write(rec.knx_obj, value)
                HDL.chanregreply(channel,value)
                return
            end
        end
        
    elseif packet.opcode == HDL.cmd.scene then   
        area = packet.additional:byte(1)
        scene = packet.additional:byte(2)

        log('scene',area,scene)
     
        for index, rec in ipairs(hdltoknx) do
            if packet.dstsubnet == rec.hdl_net and packet.dstdevice == rec.hdl_dev and area == rec.area and packet.opcode == rec.type then
                log('scene found',rec.knx_obj,scene)
                grp.write(rec.knx_obj, scene)
                HDL.scenereply(area,scene)
                return
            end
        end

	elseif packet.opcode == HDL.cmd.sequence then   
        area = packet.additional:byte(1)
        seq = packet.additional:byte(2)

        log('sequence',area,seq)
        
        for index, rec in ipairs(hdltoknx) do
            if packet.dstsubnet == rec.hdl_net and packet.dstdevice == rec.hdl_dev and area == rec.area and packet.opcode == rec.type then
                log('sequence found',rec.knx_obj,seq)
                grp.write(rec.knx_obj, seq)
                HDL.sequencereply(area,seq)
                return
            end
        end

     elseif packet.opcode == HDL.cmd.universalswitch then   
        channel = packet.additional:byte(1)
        value = packet.additional:byte(2)

        log('universalswitch',channel,value)
        
        for index, rec in ipairs(hdltoknx) do
            if packet.dstsubnet == rec.hdl_net and packet.dstdevice == rec.hdl_dev and channel == rec.channel and packet.opcode == rec.type then
                log('universalswitch found',rec.knx_obj, value)
                grp.write(rec.knx_obj, value)
                HDL.universalswitchreply(channel,value)
                return
            end
        end

   

    end
    
end

  -- check for incoming data and update knx
function hdludpread()
	local data, packet, address, chan, value, id, datatype, sendvalue
	data = hdlclient:receive()

	-- read timeout
	if not data then
        return false
	end

	log('пакет получен')

	packet,err = HDL.decode(data)
	
	if packet == nil then
		log('ошибка пакета', err)
	end

	
	
	chan = packet.additional:byte(1)
	value = packet.additional:byte(2)
	logger = string.format('src: %d.%d.%d dest: %d.%d value: %d cmd: %02X', packet.srcsubnet, packet.srcdevice, chan, packet.dstsubnet, packet.dstdevice,value, packet.opcode)

	log('hdl read',logger)

    parse(packet)
	
    return true
end


function loadmapping(url)
	s = io.readfile(url)
	local t = nil
	if s and s ~= '' then 
		t = json.pdecode(s)	
	end
		
	return t	
end 
  
 
HDL.init()
 
-- hdl connection
if hdlclient == nil then 

    hdlclient = socket.udp()
    hdlclient:settimeout(30)
    --hdlclient:setsockname(HDL.bcast, 6000)
    hdlclient:setsockname('*', 6000)

end    



lb = require('localbus').new(0.5) -- timeout is 0.5 seconds
lb:sethandler('groupwrite', knxgroupwrite)
--lb:sethandler('storage', storagecallback)
 
 
b = true 
while b do
	lb:step()
	b = hdludpread()
	os.sleep(0.05)
end


