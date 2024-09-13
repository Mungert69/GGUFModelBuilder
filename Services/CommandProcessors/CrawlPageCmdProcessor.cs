using System;
using System.Text;
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
using PuppeteerSharp;
using NetworkMonitor.Service.Services.OpenAI;

namespace NetworkMonitor.Processor.Services
{
    public class CrawlPageCmdProcessor : CmdProcessor
    {

        public CrawlPageCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
: base(logger, cmdProcessorStates, rabbitRepo, netConfig)
        {

        }
        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result = new ResultObj();
            string output = "";
            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdDisplayName} is not enabled or installed on this agent.");
                    output = $"{_cmdProcessorStates.CmdDisplayName} is not available on this agent. Try installing the Quantum Secure Agent or select an agent that has Openssl enabled.\n";
                    result.Message = await SendMessage(output, processorScanDataObj);
                    result.Success = false;
                    return result;

                }

                output = await ExtractContent(arguments);
                cancellationToken.ThrowIfCancellationRequested();
                result.Success = true;


            }
            catch (Exception e)
            {
                _logger.LogError($"Error : running {_cmdProcessorStates.CmdName} command. Errro was : {e.Message}");
                output += $"Error : running {_cmdProcessorStates.CmdName} command. Error was : {e.Message}\n";
                result.Success = false;
            }
            result.Message = output;
            return result;
        }
        private async Task RandomDelay(int min, int max)
        {
            var random = new Random();
            int delay = random.Next(min, max);
            await Task.Delay(delay);
        }

 private async Task<string> ExtractContent(string url)
{
    _logger.LogInformation("Starting browser...");

    var lo = await LaunchHelper.GetLauncher(_netConfig, _logger);
    using (var browser = await Puppeteer.LaunchAsync(lo))
    {
        var page = await browser.NewPageAsync();

        _logger.LogInformation($"Navigating to {url}");
        await page.GoToAsync(url);

        // Wait for a random delay to mimic human browsing
        await RandomDelay(2000, 5000);

        _logger.LogInformation("Waiting for page content to load...");
        await page.WaitForSelectorAsync("body");

        // Check for and handle cookie consent popups
        await HandleCookieConsent(page);

        _logger.LogInformation("Extracting content...");
        
        // Extract text content with inline links, excluding cookie and privacy-related elements
        var content = await page.EvaluateFunctionAsync<string>(@"() => {
            const unwantedKeywords = ['cookies', 'privacy', 'consent', 'accept', 'reject'];

            const getTextWithLinks = (node) => {
                let text = '';
                if (node.nodeType === Node.TEXT_NODE) {
                    return node.textContent;
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.nodeName === 'SCRIPT' || node.nodeName === 'STYLE' || 
                        node.nodeName === 'IMG' || node.nodeName === 'HEADER' || 
                        node.nodeName === 'FOOTER' || node.nodeName === 'NAV') {
                        return '';
                    }

                    // Check if element contains cookie-related keywords
                    const elementText = node.innerText || '';
                    if (unwantedKeywords.some(keyword => elementText.toLowerCase().includes(keyword))) {
                        return '';
                    }

                    if (node.nodeName === 'A') {
                        return `[${node.textContent}](${node.href})`;
                    }

                    for (let child of node.childNodes) {
                        text += getTextWithLinks(child);
                    }
                }
                return text;
            };

            // Target the main content area (article, main)
            const mainContent = document.querySelector('article, main');
            if (mainContent) {
                return getTextWithLinks(mainContent).replace(/\s\s+/g, ' ').trim();
            }

            // Fallback to body if main content not found
            return getTextWithLinks(document.body).replace(/\s\s+/g, ' ').trim();
        }");

        // Check if the extracted content is mostly cookie-related
        if (string.IsNullOrWhiteSpace(content) || 
            content.Split(' ').Length < 50 ||   // If content has too few words, assume it's not useful
            content.ToLower().Contains("cookies"))  // Check if cookies are still mentioned
        {
            _logger.LogWarning("Page content is mostly cookie notifications.");
            return "No useful content found, mostly cookie or privacy-related text.";
        }

        _logger.LogInformation("Page content extracted.");
        return content;
    }
}

// Helper function to handle cookie consent
private async Task HandleCookieConsent(IPage page)
{
    _logger.LogInformation("Checking for cookie consent popup...");

    // Common selectors for cookie banners
    var cookieSelectors = new[]
    {
        "button#accept-cookies",           // Example: Cookie banner with accept button
        "button.cookie-consent-accept",    // Example: Another potential button
        "div.cookie-banner button",        // Generic selector for cookie consent
        "button[title='Accept Cookies']",  // Example: Title attribute for acceptance
    };

    foreach (var selector in cookieSelectors)
    {
        try
        {
            var button = await page.QuerySelectorAsync(selector);
            if (button != null)
            {
                _logger.LogInformation("Cookie consent button found, clicking...");
                await button.ClickAsync();
                await page.WaitForNavigationAsync();  // Wait for any potential page reload
                _logger.LogInformation("Cookie consent accepted.");
                break;
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"Failed to handle cookie consent: {ex.Message}");
        }
    }
}



    }



}