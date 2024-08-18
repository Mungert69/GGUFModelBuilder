using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using NetworkMonitor.Utils;
using System.Xml.Linq;
using System.IO;
using System.Threading;

namespace NetworkMonitor.Processor.Services
{
    public class NmapScanProcessor : IScanProcessor
    {
        private readonly ILogger _logger;
        private readonly LocalScanProcessorStates _scanProcessorStates;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;
        private CancellationTokenSource _cancellationTokenSource;

        public bool UseDefaultEndpoint { get => _scanProcessorStates.UseDefaultEndpointType; set => _scanProcessorStates.UseDefaultEndpointType = value; }
        public NmapScanProcessor(ILogger logger, LocalScanProcessorStates scanProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _logger = logger;
            _scanProcessorStates = scanProcessorStates;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _scanProcessorStates.OnStartScanAsync += Scan;
            _scanProcessorStates.OnCancelScanAsync += CancelScan;
            _scanProcessorStates.OnAddServicesAsync += AddServices;

        }

        public void Dispose()
        {
            _scanProcessorStates.OnStartScanAsync -= Scan;
            _scanProcessorStates.OnCancelScanAsync -= CancelScan;
            _scanProcessorStates.OnAddServicesAsync -= AddServices;
            _cancellationTokenSource?.Dispose();
        }


        public async Task Scan()
        {
            try
            {
                _scanProcessorStates.IsRunning = true;
                _cancellationTokenSource = new CancellationTokenSource();
                CancellationToken cancellationToken = _cancellationTokenSource.Token;


                var selectedInterface = _scanProcessorStates.SelectedNetworkInterface;
                if (selectedInterface == null)
                {
                    throw new Exception("No network interface selected.");
                }

                var networkRange = $"{selectedInterface.IPAddress}/{selectedInterface.CIDR}";

                _logger.LogInformation($"Starting service scan on network range: {networkRange}");
                _scanProcessorStates.RunningMessage += $"Starting service scan on network range: {networkRange}\n";

                var nmapOutput = await RunScanCommand($" -sn {networkRange}", cancellationToken);
                var hosts = ParseNmapOutput(nmapOutput);

                _logger.LogInformation($"Found {hosts.Count} hosts");
                _scanProcessorStates.RunningMessage += $"Found {hosts.Count} hosts\n";

                foreach (var host in hosts)
                {
                    cancellationToken.ThrowIfCancellationRequested(); // Check for cancellation
                    await ScanHostServices(host, cancellationToken);
                }
                _scanProcessorStates.CompletedMessage += "Service scan completed successfully.\n";

                _scanProcessorStates.IsSuccess = true;
            }
            catch (OperationCanceledException)
            {
                _logger.LogInformation("Scan was cancelled.");
                _scanProcessorStates.CompletedMessage += "Scan was cancelled.\n";
                _scanProcessorStates.IsSuccess = false;
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during service scan: {e.Message}");
                _scanProcessorStates.CompletedMessage += $"Error during service scan: {e.Message}\n";
                _scanProcessorStates.IsSuccess = false;
            }
            finally
            {
                _scanProcessorStates.IsRunning = false;
            }
        }

        public async Task AddServices()
        {
            try
            {
                var selectedDevices = _scanProcessorStates.SelectedDevices.ToList();
                if (selectedDevices != null && selectedDevices.Count > 0)
                {
                    var processorDataObj = new ProcessorDataObj();
                    processorDataObj.AppID = _netConfig.AppID;
                    processorDataObj.AuthKey = _netConfig.AuthKey;
                    processorDataObj.RabbitPassword = _netConfig.LocalSystemUrl.RabbitPassword;
                    processorDataObj.MonitorIPs = selectedDevices;
                    await _rabbitRepo.PublishAsync<ProcessorDataObj>("saveMonitorIPs", processorDataObj);

                    _scanProcessorStates.CompletedMessage += $"\nSent {selectedDevices.Count} host services to Free Network Monitor Service. Please wait 2 mins for hosts to become live. You can view the in the Host Data menu or visit https://freenetworkmonitor.click/dashboard and login using the same email address you registered your agent with.\n";
                }
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during add services: {e.Message}");
                _scanProcessorStates.CompletedMessage += $"Error during add services: {e.Message}\n";
                _scanProcessorStates.IsSuccess = false;
            }

        }

        private async Task CancelScan()
        {
            if (_scanProcessorStates.IsRunning && _cancellationTokenSource != null)
            {
                _logger.LogInformation("Cancelling the ongoing scan.");
                _scanProcessorStates.RunningMessage += "Cancelling the ongoing scan...\n";
                _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation("No scan is currently running.");
                _scanProcessorStates.CompletedMessage += "No scan is currently running.\n";
            }
        }

        public async Task<string> RunScanCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            string nmapPath = "";
            if (!String.IsNullOrEmpty(_netConfig.OqsProviderPath) && !_netConfig.OqsProviderPath.Equals("/usr/local/lib/"))
            {
                nmapPath = _netConfig.OqsProviderPath.Replace("lib64", "bin");
                if (!nmapPath.EndsWith(Path.DirectorySeparatorChar.ToString()))
                {
                    nmapPath += Path.DirectorySeparatorChar;
                }
            }
            string nmapDataDir = nmapPath.Replace("bin", "share/nmap");
            string xmlOutput = "";
            if (processorScanDataObj == null) xmlOutput =" -oX -";
            using (var process = new Process())
            {
                process.StartInfo.FileName = nmapPath + "nmap";
                process.StartInfo.Arguments = arguments + xmlOutput;
                process.StartInfo.UseShellExecute = false;
                process.StartInfo.RedirectStandardOutput = true;
                process.StartInfo.CreateNoWindow = true;
                process.StartInfo.WorkingDirectory = nmapPath;

                // Start the process
                process.Start();

                // Register a callback to kill the process if cancellation is requested
                using (cancellationToken.Register(() =>
                {
                    if (!process.HasExited)
                    {
                        _logger.LogInformation("Cancellation requested, killing the Nmap process...");
                        process.Kill();
                    }
                }))
                {
                    // Read the output asynchronously, supporting cancellation
                    string output = await process.StandardOutput.ReadToEndAsync().ConfigureAwait(false);

                    // Wait for the process to exit
                    await process.WaitForExitAsync().ConfigureAwait(false);

                    // Throw if cancellation was requested after the process started
                    cancellationToken.ThrowIfCancellationRequested();

                    if (processorScanDataObj == null) return output;
                    else
                    {
                        try
                        {
                            processorScanDataObj.ScanCommandOutput = output.Replace("\n"," ");
                            await _rabbitRepo.PublishAsync<ProcessorScanDataObj>(processorScanDataObj.CallingService, processorScanDataObj);

                        }

                        catch (Exception e)
                        {
                            output = $"Error during publish nmap scan command output: {e.Message}";
                            _logger.LogError(output);

                        }
                        return output;


                    }
                }
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

        private async Task ScanHostServices(string host, CancellationToken cancellationToken)
        {
            _logger.LogInformation($"Scanning services on host: {host}");
            _scanProcessorStates.RunningMessage += $"Scanning services on host: {host}\n";
            string fastScanArg = "";
            string limitPortsArg = "";
            if (_scanProcessorStates.UseFastScan) fastScanArg = " --version-light";
            if (_scanProcessorStates.LimitPorts) limitPortsArg = " -F";

            var nmapOutput = await RunScanCommand($"{limitPortsArg}{fastScanArg} -sV {host}", cancellationToken);

            var services = ParseNmapServiceOutput(nmapOutput, host);

            foreach (var service in services)
            {
                _scanProcessorStates.ActiveDevices.Add(service);
                string message = $"Added service: {service.Address} on port {service.Port} for host {host} using endpoint type {service.EndPointType}\n";
                _scanProcessorStates.CompletedMessage += message;
                _logger.LogInformation(message);

            }
        }
        private List<MonitorIP> ParseNmapServiceOutput(string output, string host)
        {
            _logger.LogInformation($"nmap output was : {output}");
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
                if (_scanProcessorStates.UseDefaultEndpointType) endPointType = _scanProcessorStates.DefaultEndpointType;
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
                if (_scanProcessorStates.UseDefaultEndpointType) endPointType = _scanProcessorStates.DefaultEndpointType;
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