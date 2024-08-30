using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.NetworkInformation;
using System.Net;
using System.Threading.Tasks;
using System.Net.Sockets;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using NetworkMonitor.Utils;
using System.Threading;

namespace NetworkMonitor.Processor.Services;

public class PingCmdProcessor : CmdProcessor
{


    public PingCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
     : base(logger, cmdProcessorStates, rabbitRepo, netConfig)
    {
        _cmdProcessorStates.CmdName = "ping";
         _cmdProcessorStates.CmdDisplayName = "Ping";
    }


    public override async Task Scan()
    {
        string message = "";
        try
        {
            _cmdProcessorStates.IsRunning = true;
            var (localIP, subnetMask, cidr) = NetworkUtils.GetLocalIPAddressAndSubnetMask(_logger, _cmdProcessorStates);
            var (networkAddress, startIP, endIP) = NetworkUtils.GetNetworkRange(localIP, subnetMask);
            int timeout = 1000; // Ping timeout in milliseconds

            message = $"Pinging range: {NetworkUtils.IntToIp(networkAddress + startIP)} - {NetworkUtils.IntToIp(networkAddress + endIP)}\n";
            _logger.LogInformation(message);
            _cmdProcessorStates.RunningMessage += message;

            List<Task> pingTasks = new List<Task>();
            for (int i = startIP; i <= endIP; i++)
            {
                string ip = NetworkUtils.IntToIp(networkAddress + i);
                pingTasks.Add(PingAndResolveAsync(ip, timeout, _cmdProcessorStates.ActiveDevices, _cmdProcessorStates.PingInfos));
            }

            await Task.WhenAll(pingTasks);
            message = "\n Found devices up in the network:\n";
            _logger.LogInformation(message);
            _cmdProcessorStates.RunningMessage += message;

            _cmdProcessorStates.IsSuccess = true;
            var monitorIPs = _cmdProcessorStates.ActiveDevices.ToList();
            foreach (var monitorIP in monitorIPs)
            {
                monitorIP.AppID = _netConfig.AppID;
                monitorIP.UserID = _netConfig.Owner;
                monitorIP.Timeout = 59000;
                monitorIP.AgentLocation = _netConfig.MonitorLocation;
                monitorIP.DateAdded = DateTime.UtcNow;
                monitorIP.Enabled = true;
                monitorIP.EndPointType = _cmdProcessorStates.DefaultEndpointType;
                monitorIP.Hidden = false;
                monitorIP.Port = 0;
                message = $"IP Address: {monitorIP.Address}, Hostname: {monitorIP.MessageForUser}\n";
                _cmdProcessorStates.CompletedMessage += message;
                _logger.LogInformation(message);
            }

            _logger.LogInformation("Ping Information:");
            foreach (var pingInfo in _cmdProcessorStates.PingInfos)
            {
                _logger.LogInformation($"IP: {pingInfo.MonitorPingInfoID}, Status: {pingInfo.Status}, Time: {pingInfo.RoundTripTime}ms");
            }
            var processorDataObj = new ProcessorDataObj();
            processorDataObj.AppID = _netConfig.AppID;
            processorDataObj.AuthKey = _netConfig.AuthKey;
            processorDataObj.RabbitPassword = _netConfig.LocalSystemUrl.RabbitPassword;
            processorDataObj.MonitorIPs = monitorIPs;
            await _rabbitRepo.PublishAsync<ProcessorDataObj>("saveMonitorIPs", processorDataObj);
            message = $"\nSent {monitorIPs.Count} hosts to Free Network Monitor Service. Please wait 2 mins for hosts to become live. You can view the in the Host Data menu or visit https://freenetworkmonitor.click/dashboard and login using the same email address you registered your agent with.\n";
            _logger.LogInformation(message);
            _cmdProcessorStates.RunningMessage += message;
        }
        catch (Exception e)
        {
            message = $" Error : Failed to scan for local hosts. Error was :{e.Message}\n";
            _logger.LogError(message);
            _cmdProcessorStates.CompletedMessage += message;
            _cmdProcessorStates.IsSuccess = false;
        }
        finally
        {
            _cmdProcessorStates.IsRunning = false;
        }

    }


    private async Task PingAndResolveAsync(string ip, int timeout, ConcurrentBag<MonitorIP> activeDevices, ConcurrentBag<PingInfo> pingInfos)
    {
        using (Ping ping = new Ping())
        {
            try
            {
                PingReply reply = await ping.SendPingAsync(ip, timeout);
                var pingInfo = new PingInfo
                {
                    MonitorPingInfoID = NetworkUtils.IpToInt(ip),
                    DateSent = DateTime.UtcNow,
                    Status = reply.Status.ToString(),
                    RoundTripTime = (ushort?)reply.RoundtripTime
                };

                if (reply.Status == IPStatus.Success)
                {
                    string hostname = ResolveHostName(ip);

                    var monitorIP = new MonitorIP
                    {
                        Address = ip,
                        MessageForUser = hostname
                    };
                    activeDevices.Add(monitorIP);
                }

                pingInfos.Add(pingInfo);
            }
            catch (Exception ex)
            {
                var pingInfo = new PingInfo
                {
                    MonitorPingInfoID = NetworkUtils.IpToInt(ip),
                    DateSent = DateTime.UtcNow,
                    Status = $"Error: {ex.Message}",
                    RoundTripTime = 0
                };
                pingInfos.Add(pingInfo);
            }
        }
    }

    public override async Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
    {
        _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName}  Run Command is not enabled or installed on this agent.");
                var output = $"The {_cmdProcessorStates.CmdDisplayName}   Run Command is not available on this agent. Try using another agent.\n";
                _cmdProcessorStates.IsCmdSuccess = false;
                _cmdProcessorStates.IsCmdRunning = false;
                return await SendMessage(output, null);
    }
    

   

    private string ResolveHostName(string ipAddress)
    {
        try
        {
            IPHostEntry entry = Dns.GetHostEntry(ipAddress);
            return entry.HostName;
        }
        catch (Exception)
        {
            return "N/A";
        }
    }
}
