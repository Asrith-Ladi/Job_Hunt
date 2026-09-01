# 037 - Gmail batching and Network registry recovery

## Reported behavior

- A one-day LinkedIn/Naukri Gmail search remained in the Gmail-reading stage for more than two minutes and showed `0 / 2` completed.
- Network Reviews displayed a generic operation failure instead of the saved LinkedIn connection rows.

## Implemented correction

Gmail still performs one explicit read-only search and parses every selected alert, but it now:

- lists matching message identities through the official Gmail API;
- downloads full bodies in bounded groups of 25 through the official batch transport;
- retries only a partial batch failure once through an individual request;
- applies a 30-second timeout to each Google HTTP request;
- reports discovered and downloaded message counts before parsing starts;
- keeps Gmail identities, subjects, bodies, and links out of progress events and logs.

Network Reviews still reads the private local cache of the Drive-authoritative registry. If Excel or Drive omits the optional worksheet-dimension cache, the loader calculates bounds from the worksheet XML stream in read-only mode. It does not modify or upload the workbook.

## Real-cache verification

- The current registry loaded 3,486 named connections, 3,448 saved LinkedIn profiles, and 111 explicitly permitted private-UI email values.
- Its first API load completed successfully; cached API reads completed in under 100 ms locally.
- A real read-only one-day Gmail search completed in 5.96 seconds, reading 10 alert messages and returning 58 normalized job rows with no parsing warnings.

## Status

Complete. No Google scope change, LLM call, Drive write, LinkedIn scraping, or contact automation was introduced.
