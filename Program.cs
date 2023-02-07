using Microsoft.AspNetCore;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System;
using System.Net;

namespace NetworkMonitor.Processor
{
    public class Program
    {
        public static void Main(string[] args)
        {
            IConfigurationRoot config = new ConfigurationBuilder()
        .AddJsonFile("appsettings.json", optional: false)
        .Build();
            IWebHost host = CreateWebHostBuilder(args).Build();
            host.Run();
        }

        public static IWebHostBuilder CreateWebHostBuilder(string[] args) =>


        WebHost.CreateDefaultBuilder(args).UseKestrel(options =>
    {
        //options.Listen(IPAddress.Loopback, 5000);  // http:localhost:5000
        options.Listen(IPAddress.Any, 2054);         // http:*:65123
        options.Listen(IPAddress.Any, 2055);
    }).UseStartup<Startup>();
    }
}
