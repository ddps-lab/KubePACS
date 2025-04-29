data "aws_availability_zones" "available_az" {
  state = "available"
  filter {
    name   = "zone-type"
    values = ["availability-zone"]
  }
}
