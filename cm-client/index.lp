<div class="container">
  <a href="/apps/" class="button">← Back</a>
  <h2>Cottage Monitoring</h2>

  <div class="button-group">
    <button id="export-file-btn" class="button">Выгрузить все объекты в файл</button>
    <button id="export-mqtt-btn" class="button">Выгрузить все объекты в MQTT</button>
  </div>

  <p id="export-status"></p>
</div>

<script>
(function() {
  var statusEl = $('#export-status');

  $('#export-file-btn').on('click', function() {
    statusEl.text('Формирование...');
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
          statusEl.text('Скачивание началось.');
        } catch (e) {
          statusEl.text('Ошибка: ' + e);
        }
      },
      error: function() {
        statusEl.text('Ошибка загрузки.');
      }
    });
  });

  $('#export-mqtt-btn').on('click', function() {
    $.ajax({
      url: 'export_mqtt.lp',
      method: 'GET',
      success: function(resp) {
        var r = (typeof resp === 'string') ? (function() { try { return JSON.parse(resp); } catch(e) { return { ok: false, msg: resp }; } })() : resp;
        if (r && r.mqtt_connected) {
          statusEl.text('Выгрузка в MQTT запрошена.');
        } else {
          statusEl.text(r && r.msg ? r.msg : 'MQTT недоступен');
        }
      },
      error: function() {
        statusEl.text('MQTT недоступен');
      }
    });
  });
})();
</script>
