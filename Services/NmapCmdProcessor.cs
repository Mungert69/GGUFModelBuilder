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
    public class NmapCmdProcessor : ICmdProcessor
    {
        private readonly ILogger _logger;
        private readonly ILocalCmdProcessorStates _cmdProcessorStates;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;
        private CancellationTokenSource _cancellationTokenSource;

        public bool UseDefaultEndpoint { get => _cmdProcessorStates.UseDefaultEndpointType; set => _cmdProcessorStates.UseDefaultEndpointType = value; }
        public NmapCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _logger = logger;
            _cmdProcessorStates = cmdProcessorStates;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _cmdProcessorStates.OnStartScanAsync += Scan;
            _cmdProcessorStates.OnCancelScanAsync += CancelScan;
            _cmdProcessorStates.OnAddServicesAsync += AddServices;
            _cmdProcessorStates.CmdName = "nmap";

        }

        public void Dispose()
        {
            _cmdProcessorStates.OnStartScanAsync -= Scan;
            _cmdProcessorStates.OnCancelScanAsync -= CancelScan;
            _cmdProcessorStates.OnAddServicesAsync -= AddServices;
            _cancellationTokenSource?.Dispose();
        }

        public async Task Scan()
        {
            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning(" Warning : Nmape is not enabled or installed on this agent.");
                    var output = "The scan command is not available on this agent. Try using another agent.\n";
                    _cmdProcessorStates.IsSuccess = false;
                    _cmdProcessorStates.IsRunning = false;
                    await SendMessage(output, null);
                    return;

                }


                _cmdProcessorStates.IsRunning = true;
                _cancellationTokenSource = new CancellationTokenSource();
                CancellationToken cancellationToken = _cancellationTokenSource.Token;


                var selectedInterface = _cmdProcessorStates.SelectedNetworkInterface;
                if (selectedInterface == null)
                {
                    throw new Exception("No network interface selected.");
                }

                var networkRange = $"{selectedInterface.IPAddress}/{selectedInterface.CIDR}";

                _logger.LogInformation($"Starting service scan on network range: {networkRange}");
                _cmdProcessorStates.RunningMessage += $"Starting service scan on network range: {networkRange}\n";

                var nmapOutput = await RunCommand($" -sn {networkRange}", cancellationToken);
                var hosts = ParseNmapOutput(nmapOutput);

                _logger.LogInformation($"Found {hosts.Count} hosts");
                _cmdProcessorStates.RunningMessage += $"Found {hosts.Count} hosts\n";

                foreach (var host in hosts)
                {
                    cancellationToken.ThrowIfCancellationRequested(); // Check for cancellation
                    await ScanHostServices(host, cancellationToken);
                }
                _cmdProcessorStates.CompletedMessage += "Service scan completed successfully.\n";

                _cmdProcessorStates.IsSuccess = true;
            }
            catch (OperationCanceledException)
            {
                _logger.LogInformation("Scan was cancelled.");
                _cmdProcessorStates.CompletedMessage += "Scan was cancelled.\n";
                _cmdProcessorStates.IsSuccess = false;
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during service scan: {e.Message}");
                _cmdProcessorStates.CompletedMessage += $"Error during service scan: {e.Message}\n";
                _cmdProcessorStates.IsSuccess = false;
            }
            finally
            {
                _cmdProcessorStates.IsRunning = false;
            }
        }

        public async Task AddServices()
        {

            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning(" Warning : Nmape is not enabled or installed on this agent.");
                    var output = "The scan command is not available on this agent. Try using another agent.\n";
                    _cmdProcessorStates.IsSuccess = false;
                    _cmdProcessorStates.IsRunning = false;
                    await SendMessage(output, null);
                    return;

                }
                var selectedDevices = _cmdProcessorStates.SelectedDevices.ToList();
                if (selectedDevices != null && selectedDevices.Count > 0)
                {
                    var processorDataObj = new ProcessorDataObj();
                    processorDataObj.AppID = _netConfig.AppID;
                    processorDataObj.AuthKey = _netConfig.AuthKey;
                    processorDataObj.RabbitPassword = _netConfig.LocalSystemUrl.RabbitPassword;
                    processorDataObj.MonitorIPs = selectedDevices;
                    await _rabbitRepo.PublishAsync<ProcessorDataObj>("saveMonitorIPs", processorDataObj);

                    _cmdProcessorStates.CompletedMessage += $"\nSent {selectedDevices.Count} host services to Free Network Monitor Service. Please wait 2 mins for hosts to become live. You can view the in the Host Data menu or visit https://freenetworkmonitor.click/dashboard and login using the same email address you registered your agent with.\n";
                }
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during add services: {e.Message}");
                _cmdProcessorStates.CompletedMessage += $"Error during add services: {e.Message}\n";
                _cmdProcessorStates.IsSuccess = false;
            }

        }

        private async Task CancelScan()
        {
            if (!_cmdProcessorStates.IsCmdAvailable)
            {
                _logger.LogWarning(" Warning : Nmape is not enabled or installed on this agent.");
                var output = "The scan command is not available on this agent. Try using another agent.\n";
                _cmdProcessorStates.IsSuccess = false;
                _cmdProcessorStates.IsRunning = false;
                await SendMessage(output, null);
                return;

            }
            if (_cmdProcessorStates.IsRunning && _cancellationTokenSource != null)
            {
                _logger.LogInformation("Cancelling the ongoing scan.");
                _cmdProcessorStates.RunningMessage += "Cancelling the ongoing scan...\n";
                if (_cancellationTokenSource != null) _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation("No scan is currently running.");
                _cmdProcessorStates.CompletedMessage += "No scan is currently running.\n";
            }
        }

        public async Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {

            if (!_cmdProcessorStates.IsCmdAvailable)
            {
                _logger.LogWarning(" Warning : Nmap is not enabled or installed on this agent.");
                var output = "The scan command is not available on this agent. Try using another agent.\n";
                _cmdProcessorStates.IsSuccess = false;
                _cmdProcessorStates.IsRunning = false;
                return await SendMessage(output, processorScanDataObj);

            }
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
            if (processorScanDataObj == null) xmlOutput = " -oX -";
            else xmlOutput = " -oG - ";
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
                    //output += " "+await process.StandardError.ReadToEndAsync().ConfigureAwait(false);

                    // Wait for the process to exit
                    await process.WaitForExitAsync().ConfigureAwait(false);

                    // Throw if cancellation was requested after the process started
                    cancellationToken.ThrowIfCancellationRequested();
                    return await SendMessage(output, processorScanDataObj);

                }
            }
        }

        private async Task<string> SendMessage(string output, ProcessorScanDataObj? processorScanDataObj)
        {
            if (processorScanDataObj == null) return output;
            else
            {
                try
                {
                    processorScanDataObj.ScanCommandOutput = output.Replace("\n", " ");
                    await _rabbitRepo.PublishAsync<ProcessorScanDataObj>(processorScanDataObj.CallingService, processorScanDataObj);
                    _logger.LogInformation($" Success : sent output : {processorScanDataObj.ScanCommandOutput}");
                }

                catch (Exception e)
                {
                    output += $" Error : during publish nmap scan command output: {e.Message}";
                    _logger.LogError(output);

                }
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

        private async Task ScanHostServices(string host, CancellationToken cancellationToken)
        {
            _logger.LogInformation($"Scanning services on host: {host}");
            _cmdProcessorStates.RunningMessage += $"Scanning services on host: {host}\n";
            string fastScanArg = "";
            string limitPortsArg = "";
            if (_cmdProcessorStates.UseFastScan) fastScanArg = " --version-light";
            if (_cmdProcessorStates.LimitPorts) limitPortsArg = " -F";

            var nmapOutput = await RunCommand($"{limitPortsArg}{fastScanArg} -sV {host}", cancellationToken);

            var services = ParseNmapServiceOutput(nmapOutput, host);

            foreach (var service in services)
            {
                _cmdProcessorStates.ActiveDevices.Add(service);
                string message = $"Added service: {service.Address} on port {service.Port} for host {host} using endpoint type {service.EndPointType}\n";
                _cmdProcessorStates.CompletedMessage += message;
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
                if (_cmdProcessorStates.UseDefaultEndpointType) endPointType = _cmdProcessorStates.DefaultEndpointType;
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
                if (_cmdProcessorStates.UseDefaultEndpointType) endPointType = _cmdProcessorStates.DefaultEndpointType;
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