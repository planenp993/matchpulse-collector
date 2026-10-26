# MATCHPULSE Collector: SofaScore-format подготовка (v0.2)

## Какво направихме

Добавен е независим офлайн адаптер: scripts/sofascore_adapter.py.
Той **не се свързва със SofaScore** и не изтегля автоматично нищо от тях.

При получен по разрешен начин JSON експорт на футболни мачове и статистики:
- Извлича само ALL (целия мач), без да сумира първо и второ полувреме.
- Разпознава удари, точни удари, xG, корнери, жълти/червени картони и владение.
- Запазва реалните нули и оставя липсващите данни празни.
- Не приема противоречиви стойности, аномалии или съмнително съпоставени мачове.
- Показва часа на срещата по Europe/Sofia, без да изменя източника.
- Свързва към текущия колектор само при изрично съпоставяне SofaScore event ID → MATCHPULSE match ID, съвпадащи отбори, дата и резултат.
- Всички експортни файлове по подразбиране остават локални (изключени от Git).

## Важна граница на достъпа

SofaScore официално заявява, че не предоставя публичен API за повторно използване на футболни данни:
https://sofascore.helpscoutdocs.com/article/129-does-sofascore-offer-sports-data-api?lng=en

Някои технически адреси са документирани от външни разработчици, но това не е разрешение за автоматично копиране.
Затова НЕ сме пуснали робот, който обхожда SofaScore, и НЕ сме качвали техни данни в това публично репо.

## Пример за входен формат (технически)

{
  "events": [
    {
      "event": {
        "id": 12345, "startTimestamp": 1780257600,
        "homeTeam": {"name": "Arsenal"},
        "awayTeam": {"name": "Chelsea"},
        "status": {"type": "finished"},
        "homeScore": {"current": 2}, "awayScore": {"current": 1}
      },
      "statistics": {
        "statistics": [{
          "period": "ALL",
          "groups": [{"statisticsItems": [
            {"key":"totalShotsOnGoal","homeValue":14,"awayValue":10},
            {"key":"shotsOnGoal","homeValue":6,"awayValue":3},
            {"key":"expectedGoals","homeValue":1.72,"awayValue":0.88}
          ]}]
        }]
      }
    }
  ]
}

**Това е изцяло измислен тестов мач**, не действителна прогноза или получен SofaScore запис.

## Следваща стъпка

Намираме източник с изрично разрешена автоматична употреба и подробни статистики.
При предоставен разрешен експорт / договорен API свързваме автоматичното получаване към вече готовия адаптер.
Дотогава OpenFootball продължава да събира програма и резултати самостоятелно.

### Команда само за разработчик

python -m scripts.sofascore_adapter --input local/authorized_events.json --mapping local/id_map.json --snapshot data/latest.json --permission-note "explicit permitted source" --output local/sofascore_import.json

Няма нужда потребителят да използва конзола.
