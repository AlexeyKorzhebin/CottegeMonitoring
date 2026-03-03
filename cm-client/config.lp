<form id="cottage-monitoring-config" class="form-horizontal">
  <div class="form-group">
    <label for="cottage-monitoring-house_id">House ID</label>
    <input type="text" id="cottage-monitoring-house_id" class="form-control" placeholder="house-01">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-device_id">Device ID</label>
    <input type="text" id="cottage-monitoring-device_id" class="form-control" placeholder="lm-main">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-env_mode">Environment</label>
    <select id="cottage-monitoring-env_mode" class="form-control">
      <option value="prod">prod</option>
      <option value="dev">dev</option>
    </select>
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-mqtt_host">MQTT Host</label>
    <input type="text" id="cottage-monitoring-mqtt_host" class="form-control" placeholder="elion.black-castle.ru">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-mqtt_port">MQTT Port</label>
    <input type="number" id="cottage-monitoring-mqtt_port" class="form-control" min="1" max="65535" placeholder="8883">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-mqtt_username">MQTT Username</label>
    <input type="text" id="cottage-monitoring-mqtt_username" class="form-control">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-mqtt_password">MQTT Password</label>
    <input type="password" id="cottage-monitoring-mqtt_password" class="form-control">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-mqtt_use_tls">TLS</label>
    <input type="checkbox" id="cottage-monitoring-mqtt_use_tls" checked disabled title="TLS always enabled">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-client_id">Client ID (optional)</label>
    <input type="text" id="cottage-monitoring-client_id" class="form-control" placeholder="auto" maxlength="64">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-debug">Debug</label>
    <input type="checkbox" id="cottage-monitoring-debug">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-snapshot_interval">Snapshot interval (s, 0=off)</label>
    <input type="number" id="cottage-monitoring-snapshot_interval" class="form-control" min="0" value="0">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-throttle">Throttle (events/s, 0=unlimited)</label>
    <input type="number" id="cottage-monitoring-throttle" class="form-control" min="0" value="0">
  </div>
  <div class="form-group">
    <label for="cottage-monitoring-buffer_size">Buffer size (offline, 0=disabled)</label>
    <input type="number" id="cottage-monitoring-buffer_size" class="form-control" min="0" value="1000">
  </div>
</form>

<script>
(function() {
  var el = $('#cottage-monitoring-config');
  var APP = 'cottage-monitoring';

  el.on('config-load', function(event, data) {
    if (!data) return;
    $.each(data, function(key, value) {
      var field = $('#' + APP + '-' + key);
      if (field.length === 0) return;
      if (field.attr('type') === 'checkbox') {
        field.prop('checked', value === true || value === 'true' || value === '1');
      } else {
        field.val(value !== undefined && value !== null ? value : '');
      }
    });
  });

  function validId(s, name) {
    if (!s || typeof s !== 'string') return false;
    if (s.length > 64) return false;
    return /^[a-zA-Z0-9_-]+$/.test(s);
  }

  el.on('config-check', function() {
    var house_id = $.trim($('#' + APP + '-house_id').val());
    var device_id = $.trim($('#' + APP + '-device_id').val());
    var env_mode = $('#' + APP + '-env_mode').val();
    var mqtt_host = $.trim($('#' + APP + '-mqtt_host').val());
    var mqtt_port = parseInt($('#' + APP + '-mqtt_port').val(), 10);
    var mqtt_username = $.trim($('#' + APP + '-mqtt_username').val());
    var mqtt_password = $('#' + APP + '-mqtt_password').val();
    var snapshot_interval = parseInt($('#' + APP + '-snapshot_interval').val(), 10) || 0;
    var throttle = parseInt($('#' + APP + '-throttle').val(), 10) || 0;
    var buffer_size = parseInt($('#' + APP + '-buffer_size').val(), 10) || 0;

    if (!validId(house_id, 'house_id')) {
      alert('house_id: 1-64 chars [a-zA-Z0-9_-]');
      return;
    }
    if (!validId(device_id, 'device_id')) {
      alert('device_id: 1-64 chars [a-zA-Z0-9_-]');
      return;
    }
    if (env_mode !== 'dev' && env_mode !== 'prod') {
      alert('env_mode must be dev or prod');
      return;
    }
    if (!mqtt_host) {
      alert('mqtt_host is required');
      return;
    }
    if (isNaN(mqtt_port) || mqtt_port < 1 || mqtt_port > 65535) {
      alert('mqtt_port: 1-65535');
      return;
    }
    if (!mqtt_username) {
      alert('mqtt_username is required');
      return;
    }
    if (!mqtt_password) {
      alert('mqtt_password is required');
      return;
    }
    if (snapshot_interval < 0) {
      alert('snapshot_interval must be >= 0');
      return;
    }
    if (throttle < 0) {
      alert('throttle must be >= 0');
      return;
    }
    if (buffer_size < 0) {
      alert('buffer_size must be >= 0');
      return;
    }

    var client_id = $.trim($('#' + APP + '-client_id').val());
    var debug = $('#' + APP + '-debug').prop('checked');

    el.triggerHandler('config-save', {
      house_id: house_id,
      device_id: device_id,
      env_mode: env_mode,
      mqtt_host: mqtt_host,
      mqtt_port: mqtt_port,
      mqtt_username: mqtt_username,
      mqtt_password: mqtt_password,
      mqtt_use_tls: true,
      client_id: client_id,
      debug: debug,
      snapshot_interval: snapshot_interval,
      throttle: throttle,
      buffer_size: buffer_size
    });

    $.get('/apps/request.lp?action=restart&name=cottage-monitoring');
  });
})();
</script>
