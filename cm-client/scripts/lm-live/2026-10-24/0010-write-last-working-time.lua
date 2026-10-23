
t = os.time(os.date("*t"))

--log(os.date("*%c", t))

storage.set('system.last_working_time', t)
