data "azurerm_monitor_action_group" "ccoe_budget_alert" {
  name                = var.action_group_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_monitor_activity_log_alert" "service_request_alert" {
  name                = var.alert_name
  resource_group_name = var.resource_group_name
  scopes              = ["/subscriptions/${var.subscription_id}"]
  description         = "Alert when a Support Ticket is created/written."
  location = var.location


  criteria {
    operation_name = "Microsoft.Support/supportTickets/write"
    category       = "Administrative" 
  }

  action {
    action_group_id = data.azurerm_monitor_action_group.ccoe_budget_alert.id
  }
}