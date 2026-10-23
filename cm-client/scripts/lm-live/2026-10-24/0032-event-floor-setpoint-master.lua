
floors = grp.tag({'heat', 'setpoint', 'temp'}, 'all')
log(floors)

floors:update(event.getvalue())
--log(event.getvalue())