<link rel="stylesheet" href="style.css">
<script src="/apps/js/jquery.js.gz"></script>

<div class="cm-app">
  <a href="/apps/" class="cm-back">← Назад</a>
  <h1 class="cm-title">Cottage Monitoring</h1>

  <div class="cm-card">
    <div class="cm-actions">
      <button id="export-file-btn" class="cm-btn">Выгрузить в файл</button>
      <button id="export-mqtt-btn" class="cm-btn cm-btn-secondary">Выгрузить в MQTT</button>
    </div>
    <p id="export-status" class="cm-status"></p>
  </div>

  <div class="cm-card">
    <button type="button" class="cm-config-toggle" id="config-toggle" aria-expanded="false" aria-controls="config-body">Параметры подключения</button>
    <div id="config-body" class="cm-config-body" style="display:none;">
      <form id="cottage-monitoring-config">
        <div class="cm-field">
          <label for="cottage-monitoring-house_id">House ID</label>
          <input type="text" id="cottage-monitoring-house_id" placeholder="house-01">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-device_id">Device ID</label>
          <input type="text" id="cottage-monitoring-device_id" placeholder="lm-main">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-env_mode">Environment</label>
          <select id="cottage-monitoring-env_mode">
            <option value="prod">prod</option>
            <option value="dev">dev</option>
          </select>
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-mqtt_host">MQTT Host</label>
          <input type="text" id="cottage-monitoring-mqtt_host" placeholder="elion.black-castle.ru">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-mqtt_port">MQTT Port</label>
          <input type="number" id="cottage-monitoring-mqtt_port" min="1" max="65535" placeholder="8883">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-mqtt_username">MQTT Username</label>
          <input type="text" id="cottage-monitoring-mqtt_username">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-mqtt_password">MQTT Password</label>
          <input type="password" id="cottage-monitoring-mqtt_password" placeholder="введите для смены">
        </div>
        <div class="cm-field cm-field-row">
          <input type="checkbox" id="cottage-monitoring-mqtt_use_tls" checked disabled>
          <label for="cottage-monitoring-mqtt_use_tls">TLS (всегда включён)</label>
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-client_id">Client ID (опц.)</label>
          <input type="text" id="cottage-monitoring-client_id" placeholder="auto" maxlength="64">
        </div>
        <div class="cm-field cm-field-row">
          <input type="checkbox" id="cottage-monitoring-debug">
          <label for="cottage-monitoring-debug">Debug</label>
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-snapshot_interval">Snapshot interval (с, 0=выкл)</label>
          <input type="number" id="cottage-monitoring-snapshot_interval" min="0" value="0">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-throttle">Throttle (events/с, 0=без лимита)</label>
          <input type="number" id="cottage-monitoring-throttle" min="0" value="30" title="30=снижает нагрузку">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-buffer_size">Buffer size (offline, 0=выкл)</label>
          <input type="number" id="cottage-monitoring-buffer_size" min="0" value="1000">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-event_sleep">Event sleep (с, 0=выкл)</label>
          <input type="number" id="cottage-monitoring-event_sleep" min="0" max="1" step="0.01" value="0.02" title="Пауза после KNX-события">
        </div>
        <div class="cm-field">
          <label for="cottage-monitoring-loop_sleep">Loop sleep (с)</label>
          <input type="number" id="cottage-monitoring-loop_sleep" min="0.01" max="0.5" step="0.01" value="0.15" title="Пауза в главном цикле">
        </div>
        <div class="cm-field">
          <button type="button" id="apply-lowload-btn" class="cm-btn">Применить настройки для снижения нагрузки</button>
          <span class="cm-help">throttle=30, event_sleep=0.02, loop_sleep=0.15</span>
        </div>
        <button type="button" id="config-save-btn" class="cm-btn cm-save">Сохранить</button>
      </form>
    </div>
  </div>
</div>

<script>
$(function() {
  var APP = 'cottage-monitoring';
  var $form = $('#cottage-monitoring-config');
  var $status = $('#export-status');
  var $configBody = $('#config-body');
  var $configToggle = $('#config-toggle');

  $configToggle.on('click', function() {
    var open = $configBody.is(':visible');
    $configBody.toggle();
    $configToggle.attr('aria-expanded', !open);
  });

  function loadConfig() {
    $.get('config_get.lp', function(data) {
      try {
        var cfg = typeof data === 'string' ? JSON.parse(data) : data;
        $.each(cfg, function(key, value) {
          if (key === 'mqtt_password') return;
          var $f = $('#' + APP + '-' + key);
          if (!$f.length) return;
          if ($f.attr('type') === 'checkbox') {
            $f.prop('checked', value === true || value === 'true' || value === '1');
          } else {
            $f.val(value !== undefined && value !== null ? value : '');
          }
        });
      } catch (e) {}
    }).fail(function() {});
  }
  loadConfig();

  function validId(s) {
    return s && typeof s === 'string' && s.length <= 64 && /^[a-zA-Z0-9_-]+$/.test(s);
  }

  $('#apply-lowload-btn').on('click', function() {
    $('#' + APP + '-throttle').val(30);
    $('#' + APP + '-event_sleep').val(0.02);
    $('#' + APP + '-loop_sleep').val(0.15);
    $status.text('Настройки вставлены. Нажмите «Сохранить».');
  });

  $('#config-save-btn').on('click', function() {
    var house_id = $.trim($('#' + APP + '-house_id').val());
    var device_id = $.trim($('#' + APP + '-device_id').val());
    var env_mode = $('#' + APP + '-env_mode').val();
    var mqtt_host = $.trim($('#' + APP + '-mqtt_host').val());
    var mqtt_port = parseInt($('#' + APP + '-mqtt_port').val(), 10);
    var mqtt_username = $.trim($('#' + APP + '-mqtt_username').val());
    var mqtt_password = $('#' + APP + '-mqtt_password').val();
    var snapshot_interval = parseInt($('#' + APP + '-snapshot_interval').val(), 10) || 0;
    var throttle = parseInt($('#' + APP + '-throttle').val(), 10) || 30;
    var buffer_size = parseInt($('#' + APP + '-buffer_size').val(), 10) || 0;
    var event_sleep = parseFloat($('#' + APP + '-event_sleep').val()) || 0.02;
    var loop_sleep = parseFloat($('#' + APP + '-loop_sleep').val()) || 0.15;

    if (!validId(house_id)) { alert('house_id: 1-64 символов [a-zA-Z0-9_-]'); return; }
    if (!validId(device_id)) { alert('device_id: 1-64 символов [a-zA-Z0-9_-]'); return; }
    if (env_mode !== 'dev' && env_mode !== 'prod') { alert('env_mode: dev или prod'); return; }
    if (!mqtt_host) { alert('mqtt_host обязателен'); return; }
    if (isNaN(mqtt_port) || mqtt_port < 1 || mqtt_port > 65535) { alert('mqtt_port: 1-65535'); return; }
    if (!mqtt_username) { alert('mqtt_username обязателен'); return; }
    if (!mqtt_password) { alert('mqtt_password обязателен'); return; }
    if (snapshot_interval < 0) { alert('snapshot_interval >= 0'); return; }
    if (throttle < 0) { alert('throttle >= 0'); return; }
    if (buffer_size < 0) { alert('buffer_size >= 0'); return; }

    var payload = {
      house_id: house_id, device_id: device_id, env_mode: env_mode,
      mqtt_host: mqtt_host, mqtt_port: mqtt_port,
      mqtt_username: mqtt_username, mqtt_password: mqtt_password,
      mqtt_use_tls: true, client_id: $.trim($('#' + APP + '-client_id').val()),
      debug: $('#' + APP + '-debug').prop('checked'),
      snapshot_interval: snapshot_interval, throttle: throttle, buffer_size: buffer_size,
      event_sleep: event_sleep, loop_sleep: loop_sleep
    };

    $.post('config_save.lp', { config: JSON.stringify(payload) })
      .done(function() {
        $.get('/apps/request.lp?action=restart&name=cottage-monitoring');
        $status.text('Конфиг сохранён, daemon перезапущен.');
      })
      .fail(function() { $status.text('Ошибка сохранения.'); });
  });

  $form.on('config-load', function(e, data) {
    if (!data) return;
    $.each(data, function(key, value) {
      var $f = $('#' + APP + '-' + key);
      if (!$f.length) return;
      if ($f.attr('type') === 'checkbox') {
        $f.prop('checked', value === true || value === 'true' || value === '1');
      } else {
        $f.val(value !== undefined && value !== null ? value : '');
      }
    });
  });

  $('#export-file-btn').on('click', function() {
    $status.text('Формирование...');
    $.ajax({
      url: 'export.lp?action=export_file',
      dataType: 'text',
      success: function(data) {
        try {
          var blob = new Blob([data], { type: 'application/json' });
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'cottage-monitoring-export.json';
          a.click();
          URL.revokeObjectURL(a.href);
          $status.text('Скачивание началось.');
        } catch (e) { $status.text('Ошибка: ' + e); }
      },
      error: function() { $status.text('Ошибка загрузки.'); }
    });
  });

  $('#export-mqtt-btn').on('click', function() {
    $.ajax({
      url: 'export_mqtt.lp',
      method: 'GET',
      success: function(resp) {
        var r = (typeof resp === 'string') ? (function() { try { return JSON.parse(resp); } catch(e) { return { ok: false, msg: resp }; } })() : resp;
        if (r && r.mqtt_connected) {
          $status.text('Выгрузка в MQTT запрошена (обычно 2–5 с)...');
          setTimeout(function() {
            $status.text('Выгрузка завершена.');
            setTimeout(function() { $status.text(''); }, 2000);
          }, 5000);
        } else {
          $status.text(r && r.msg ? r.msg : 'MQTT недоступен');
        }
      },
      error: function() { $status.text('MQTT недоступен'); }
    });
  });
});
</script>
