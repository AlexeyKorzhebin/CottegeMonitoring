-- object mapped to this event must have its data type set
value = event.getvalue()
if (value == false) then
	floors = grp.tag({'heat', 'control'}, 'all')
	floors:update(false,1)    
end

