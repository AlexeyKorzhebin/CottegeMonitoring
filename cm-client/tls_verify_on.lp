<?
-- Enable MQTT broker cert verification (ISRG Root X1).
require('apps')
config.set('cottage-monitoring', 'mqtt_tls_verify', 'true')
config.set('cottage-monitoring', 'mqtt_cafile', '/data/apps/store/data/cottage-monitoring/certs/isrg-root-x1.pem')
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print('{"mqtt_tls_verify":true}')
?>
