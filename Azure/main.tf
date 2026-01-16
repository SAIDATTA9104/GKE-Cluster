data "azurerm_monitor_action_group" "ccoe_budget_alert" {
  name                = "CCOE-Budget-Alert"
  resource_group_name = var.resource_group_name
}

resource "azurerm_monitor_activity_log_alert" "service_request_alert" {
  name                = "Service Request Alert"
  resource_group_name = var.resource_group_name
  scopes              = ["/subscriptions/${var.subscription_id}"]
  description         = "Alert when a Support Ticket is created/written."
  location = var.location


  criteria {
    # This corresponds to "Signal name: Writer Support Ticket"
    operation_name = "Microsoft.Support/supportTickets/write"
    category       = "Administrative" 
  }

  action {
    action_group_id = data.azurerm_monitor_action_group.ccoe_budget_alert.id
  }
}