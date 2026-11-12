<#
  Túnel SSH hacia CAPITAL RADAR PRO (sin exponer puertos web). La ruta de la clave y el usuario se pasan por parámetro;
  NO se guardan en el repositorio.
  Uso:  .\ssh-tunnel.ps1 -KeyPath "C:\ruta\clave.pem" -User azureuser -HostIp 20.78.0.70
  Luego abre http://localhost:8000
#>
param(
  [Parameter(Mandatory)] [string]$KeyPath,
  [Parameter(Mandatory)] [string]$User,
  [string]$HostIp = "20.78.0.70",
  [int]$LocalPort = 8000
)
if (-not (Test-Path $KeyPath)) { throw "No existe la clave indicada" }
ssh -i $KeyPath -o IdentitiesOnly=yes -o StrictHostKeyChecking=ask -N -L "${LocalPort}:127.0.0.1:8000" "$User@$HostIp"
