using NetworkMonitor.Connection;
using System.Net.Sockets;
using NetworkMonitor.Objects;
using System.Threading;
using Xunit;
using System;
namespace NetworkMonitor.Tests
{
    public class SMTPConnectTests
    {
        private MonitorPingInfo pingInfo;
        private PingParams pingParams;
        public SMTPConnectTests()
        {
            pingParams = new PingParams();
            pingParams.Timeout = 10000;
        }
        [Fact]
        public async void TestConnectionAsync_WhenConnectedToServer_ReturnsTrue()
        {
            // Arrange
            var server = "mail.mahadeva.co.uk";
            ushort port = 25;
            var cts = new CancellationTokenSource();
            cts.CancelAfter(TimeSpan.FromMilliseconds(pingParams.Timeout));
            pingInfo = new MonitorPingInfo();
            pingInfo.EndPointType = "SMTP";
            pingInfo.Timeout = 10000;
            pingInfo.Address = server;
            pingInfo.Port = port;
            // Act
            var smtpConnect = new SMTPConnect();
            //smtpConnect.PingParams = pingParams;
                        smtpConnect.MpiStatic=new MPIStatic(pingInfo);
            var result = await smtpConnect.TestConnectionAsync(port);
            // Assert
            Assert.True(result.Success);
        }
        [Fact]
        public async void Connect_WhenConnectedToServer_UpdatesMonitorPingInfo()
        {
            // Arrange
            var server = "mail.mahadeva.co.uk";
            ushort port = 25;
            pingInfo = new MonitorPingInfo();
            pingInfo.EndPointType = "SMTP";
            pingInfo.Timeout = 10000;
            pingInfo.Address = server;
            pingInfo.Port = port;
            // Act
            var smtpConnect = new SMTPConnect();
            //smtpConnect.PingParams = pingParams;
            smtpConnect.MpiStatic=new MPIStatic(pingInfo);
            await smtpConnect.Connect();
            // Assert
            Assert.Equal("Connect Ok", pingInfo.Status);
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.True(pingInfo.PingInfos.Count > 0);
        }
        [Fact]
        public async void Connect_WhenNotConnectedToServer_UpdatesMonitorPingInfoWithErrorMessage()
        {
            // Arrange
            var server = "invalid.server";
            ushort port = 25;
            pingInfo = new MonitorPingInfo();
            pingInfo.EndPointType = "SMTP";
            pingInfo.Timeout = 10000;
            pingInfo.Address = server;
            pingInfo.Port = port;
            // Act
            var smtpConnect = new SMTPConnect();
            //smtpConnect.PingParams = pingParams;
                       smtpConnect.MpiStatic=new MPIStatic(pingInfo);
            await smtpConnect.Connect();
            // Assert
            Assert.NotEqual("Connect Ok", pingInfo.Status);
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.True(pingInfo.PingInfos.Count > 0);
        }
    }
}
