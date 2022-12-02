using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using NetworkMonitorProcessor.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using System;
using Dapr.Client;
using NetworkMonitor.Auth;
using Microsoft.Extensions.Logging;

namespace NetworkMonitorProcessor
{
    public class Startup
    {
        public Startup(IConfiguration configuration)
        {
            Configuration = configuration;
        }

        public IConfiguration Configuration { get; }

        private IServiceCollection _services;

        // This method gets called by the runtime. Use this method to add services to the container.
        public void ConfigureServices(IServiceCollection services)
        {
            _services = services;
            services.AddCors(options =>
            {
                options.AddPolicy("AllowAnyOrigin",
                    builder => builder.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod());
            });
             string connectionString = Configuration.GetConnectionString("DefaultConnection");
              services.AddSingleton<IMonitorPingProcessor, MonitorPingProcessor>();

            services.Configure<HostOptions>(s => s.ShutdownTimeout = TimeSpan.FromMinutes(5));

            string domain = $"https://{Configuration["Auth0:Domain"]}/";
            services.AddAuthentication(options =>
            {
                options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
                options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;

            }).AddJwtBearer(options =>
            {
                options.Authority = domain;
                options.Audience = Configuration["Auth0:ApiIdentifier"];
            });

            services.AddAuthorization(options =>
            {
                options.AddPolicy("read:messages", policy => policy.Requirements.Add(new HasScopeRequirement("read:messages", domain)));
            });

            // register the scope authorization handler
            services.AddSingleton<IAuthorizationHandler, HasScopeHandler>();

            services.AddControllers().AddDapr();

            services.AddLogging(options =>
    {
        options.AddSimpleConsole(c =>
        {
            c.TimestampFormat = "[yyyy-MM-dd HH:mm:ss] ";
            c.UseUtcTimestamp = true;
        });
    });

        }

        // This method gets called by the runtime. Use this method to configure the HTTP request pipeline.
        public void Configure(IApplicationBuilder app, IWebHostEnvironment env, IHostApplicationLifetime applicationLifetime)
        {
          
            app.UseCors("AllowAnyOrigin");
            app.UseRouting();
            app.UseStaticFiles();
            app.UseAuthentication();
            app.UseAuthorization();
            app.UseCloudEvents();
            app.UseEndpoints(endpoints =>
            {
                endpoints.MapSubscribeHandler();
                endpoints.MapControllers();
            });
        }
    }
}
