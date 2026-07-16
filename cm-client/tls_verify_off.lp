<?
-- Disable MQTT broker cert verification (tls_insecure).
require('apps')
config.set('cottage-monitoring', 'mqtt_tls_verify', 'false')
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print('{"mqtt_tls_verify":false}')
?>
