using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Connection;
using System.Xml.Linq;

namespace NetworkMonitor.Processor.Services
{
    public class NmapScanProcessor : IScanProcessor
    {
        private readonly ILogger _logger;
        private readonly LocalScanProcessorStates _scanProcessorStates;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;
        private bool _useDefaultEndpoint = false;

        public bool UseDefaultEndpoint { get => _useDefaultEndpoint; set => _useDefaultEndpoint = value; }

        public NmapScanProcessor(ILogger logger, LocalScanProcessorStates scanProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _logger = logger;
            _scanProcessorStates = scanProcessorStates;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _scanProcessorStates.OnStartScanAsync += Scan;
        }

        public void Dispose()
        {
            _scanProcessorStates.OnStartScanAsync -= Scan;
        }

        public async Task Scan()
        {
            try
            {
                _scanProcessorStates.IsRunning = true;
                var (localIP, subnetMask, cidr) = NetworkUtils.GetLocalIPAddressAndSubnetMask(_logger, _scanProcessorStates);
                var networkRange = $"{localIP}/{cidr}";

                _logger.LogInformation($"Starting nmap scan on network range: {networkRange}");
                _scanProcessorStates.RunningMessage += $"Starting nmap scan on network range: {networkRange}\n";

                var nmapOutput = await RunNmapCommand($"-sn {networkRange}");
                var hosts = ParseNmapOutput(nmapOutput);

                _logger.LogInformation($"Found {hosts.Count} hosts");
                _scanProcessorStates.RunningMessage += $"Found {hosts.Count} hosts\n";

                foreach (var host in hosts)
                {
                    await ScanHostServices(host);
                }

                _scanProcessorStates.IsSuccess = true;
                _scanProcessorStates.CompletedMessage += "Nmap scan completed successfully.\n";
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during nmap scan: {e.Message}");
                _scanProcessorStates.CompletedMessage += $"Error during nmap scan: {e.Message}\n";
                _scanProcessorStates.IsSuccess = false;
            }
            finally
            {
                _scanProcessorStates.IsRunning = false;
            }
        }

        private async Task<string> RunNmapCommand(string arguments)
        {
            using (var process = new Process())
            {
                process.StartInfo.FileName = "nmap";
                process.StartInfo.Arguments = arguments + " -oX -";
                process.StartInfo.UseShellExecute = false;
                process.StartInfo.RedirectStandardOutput = true;
                process.StartInfo.CreateNoWindow = true;

                process.Start();
                string output = await process.StandardOutput.ReadToEndAsync();
                await process.WaitForExitAsync();

                return output;
            }
        }

        private List<string> ParseNmapOutputOld(string output)
        {
            var hosts = new List<string>();
            var regex = new Regex(@"Nmap scan report for (.+)");
            var matches = regex.Matches(output);

            foreach (Match match in matches)
            {
                hosts.Add(match.Groups[1].Value);
            }

            return hosts;
        }
        private List<string> ParseNmapOutput(string output)
        {
            var hosts = new List<string>();
            var xdoc = XDocument.Parse(output);

            var hostElements = xdoc.Descendants("host");
            foreach (var hostElement in hostElements)
            {
                var addressElement = hostElement.Descendants("address").FirstOrDefault(a => a.Attribute("addrtype")?.Value == "ipv4");
                if (addressElement != null)
                {
                    hosts.Add(addressElement.Attribute("addr").Value);
                }
            }

            return hosts;
        }

        private async Task ScanHostServices(string host)
        {
            _logger.LogInformation($"Scanning services on host: {host}");
            _scanProcessorStates.RunningMessage += $"Scanning services on host: {host}\n";

            var nmapOutput = await RunNmapCommand($"-sV {host}");
            var services = ParseNmapServiceOutput(nmapOutput, host);

            foreach (var service in services)
            {
                _scanProcessorStates.ActiveDevices.Add(service);
                _scanProcessorStates.CompletedMessage += $"Added service: {service.Address} on port {service.Port} for host {host}\n";
            }
        }
private List<MonitorIP> ParseNmapServiceOutput(string output, string host)
{
    var monitorIPs = new List<MonitorIP>();
    var xdoc = XDocument.Parse(output);

    var portElements = xdoc.Descendants("port");
    foreach (var portElement in portElements)
    {
        int port = int.Parse(portElement.Attribute("portid").Value);
        string protocol = portElement.Attribute("protocol").Value.ToLower();
        var serviceElement = portElement.Element("service");
        string serviceName = serviceElement?.Attribute("name")?.Value.ToLower() ?? "unknown";
        string version = serviceElement?.Attribute("version")?.Value ?? "unknown";

        string endPointType;
        if (_useDefaultEndpoint) endPointType = _scanProcessorStates.EndPointType;
        else endPointType = DetermineEndPointType(serviceName, protocol);

        var monitorIP = new MonitorIP
        {
            Address = host,
            Port = (ushort)port,
            EndPointType = endPointType,
            AppID = _netConfig.AppID,
            UserID = _netConfig.Owner,
            Timeout = 5000,
            AgentLocation = _netConfig.MonitorLocation,
            DateAdded = DateTime.UtcNow,
            Enabled = true,
            Hidden = false,
            MessageForUser = $"{serviceName} ({version})"
        };

        monitorIPs.Add(monitorIP);
    }

    return monitorIPs;
}
        private List<MonitorIP> ParseNmapServiceOutputOld(string output, string host)
        {
            var monitorIPs = new List<MonitorIP>();
            var regex = new Regex(@"(\d+)/(\w+)\s+(\w+)\s+(.+)");
            var matches = regex.Matches(output);

            foreach (Match match in matches)
            {
                int port = int.Parse(match.Groups[1].Value);
                string protocol = match.Groups[2].Value.ToLower();
                string serviceName = match.Groups[3].Value.ToLower();
                string version = match.Groups[4].Value;

                string endPointType;
                if (_useDefaultEndpoint) endPointType = _scanProcessorStates.EndPointType;
                else endPointType = DetermineEndPointType(serviceName, protocol);

                var monitorIP = new MonitorIP
                {
                    Address = host,
                    Port = (ushort)port,
                    EndPointType = endPointType,
                    AppID = _netConfig.AppID,
                    UserID = _netConfig.Owner,
                    Timeout = 5000,
                    AgentLocation = _netConfig.MonitorLocation,
                    DateAdded = DateTime.UtcNow,
                    Enabled = true,
                    Hidden = false,
                    MessageForUser = $"{serviceName} ({version})"
                };

                monitorIPs.Add(monitorIP);
            }

            return monitorIPs;
        }

        private string DetermineEndPointType(string serviceName, string protocol)
        {
            switch (serviceName)
            {
                case "http":
                    return "http";
                case "https":
                    return "https";
                case "domain":
                    return "dns";
                case "smtp":
                    return "smtp";
                case "ssh":
                case "telnet":
                case "ftp":
                    return "rawconnect";
                default:
                    if (protocol == "tcp")
                        return "rawconnect";
                    else
                        return "icmp";
            }
        }

    }



}