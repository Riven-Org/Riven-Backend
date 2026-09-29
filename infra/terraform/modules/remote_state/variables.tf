variable "name_prefix" {
  description = "Prefix for remote state resources (e.g. riven-tfstate-staging)"
  type        = string
}

variable "tags" {
  description = "Tags to attach to remote state resources"
  type        = map(string)
  default     = {}
}
