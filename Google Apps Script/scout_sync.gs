function onSyncSelection(e) {
    if (e.range.getA1Notation() == 'A1') {
      var response
      if (e.value == 'Kalender -> Tabelle ...') {
        response = sync_calendar_to_table()
      } else if (e.value == 'Tabelle -> Kalender ...') {
        response = sync_table_to_calendar()
      }
      
      if (response) {
        if (![200, 201].includes(response.getResponseCode())) {
          
          // SpreadsheetApp.getUi().alert(response.getContentText())
          // SpreadsheetApp.getActive().toast(response.getContentText())
          e.range.setValue("Error!")
          throw new Error(response.getContentText())
        } else {
          e.range.setValue("Sync")
        }
      }
    }
  }
  
  function sync_calendar_to_table() {
    var url = "https://scout-sync.orbinaut.repl.co/sync";
    var options = {
      "method": "post",
      "payload": {
          "from": "calendar",
          "to": "table"
      },
     "muteHttpExceptions": true
    }
    
    var response = UrlFetchApp.fetch(url, options)
    return response
  }
  
  function sync_table_to_calendar() {
    var url = "https://scout-sync.orbinaut.repl.co/sync";
    var options = {
      "method": "post",
      "payload": {
          "from": "table",
          "to": "calendar"
      },
     "muteHttpExceptions": true
    }
    
    var response = UrlFetchApp.fetch(url, options)
    return response
  }
  
  function keep_alive() {
    var url = "https://scout-sync.orbinaut.repl.co";
    var response = UrlFetchApp.fetch(url)
    return response
  }
  