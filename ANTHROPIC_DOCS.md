BATCHING DOCS:

# Batch processing

Batch processing is a powerful approach for handling large volumes of requests efficiently. Instead of processing requests one at a time with immediate responses, batch processing allows you to submit multiple requests together for asynchronous processing. This pattern is particularly useful when:

* You need to process large volumes of data
* Immediate responses are not required
* You want to optimize for cost efficiency
* You're running large-scale evaluations or analyses

The Message Batches API is our first implementation of this pattern.

***

# Message Batches API

The Message Batches API is a powerful, cost-effective way to asynchronously process large volumes of [Messages](/en/api/messages) requests. This approach is well-suited to tasks that do not require immediate responses, with most batches finishing in less than 1 hour while reducing costs by 50% and increasing throughput.

You can [explore the API reference directly](/en/api/creating-message-batches), in addition to this guide.

## How the Message Batches API works

When you send a request to the Message Batches API:

1. The system creates a new Message Batch with the provided Messages requests.
2. The batch is then processed asynchronously, with each request handled independently.
3. You can poll for the status of the batch and retrieve results when processing has ended for all requests.

This is especially useful for bulk operations that don't require immediate results, such as:

* Large-scale evaluations: Process thousands of test cases efficiently.
* Content moderation: Analyze large volumes of user-generated content asynchronously.
* Data analysis: Generate insights or summaries for large datasets.
* Bulk content generation: Create large amounts of text for various purposes (e.g., product descriptions, article summaries).

### Batch limitations

* A Message Batch is limited to either 100,000 Message requests or 256 MB in size, whichever is reached first.
* We process each batch as fast as possible, with most batches completing within 1 hour. You will be able to access batch results when all messages have completed or after 24 hours, whichever comes first. Batches will expire if processing does not complete within 24 hours.
* Batch results are available for 29 days after creation. After that, you may still view the Batch, but its results will no longer be available for download.
* Batches are scoped to a [Workspace](https://console.anthropic.com/settings/workspaces). You may view all batches—and their results—that were created within the Workspace that your API key belongs to.
* Rate limits apply to both Batches API HTTP requests and the number of requests within a batch waiting to be processed. See [Message Batches API rate limits](/en/api/rate-limits#message-batches-api). Additionally, we may slow down processing based on current demand and your request volume. In that case, you may see more requests expiring after 24 hours.
* Due to high throughput and concurrent processing, batches may go slightly over your Workspace's configured [spend limit](https://console.anthropic.com/settings/limits).

### Supported models

The Message Batches API currently supports:

* Claude Opus 4 (`claude-opus-4-20250514`)
* Claude Sonnet 4 (`claude-sonnet-4-20250514`)
* Claude Sonnet 3.7 (`claude-3-7-sonnet-20250219`)
* Claude Sonnet 3.5 (`claude-3-5-sonnet-20240620` and `claude-3-5-sonnet-20241022`)
* Claude Haiku 3.5 (`claude-3-5-haiku-20241022`)
* Claude Haiku 3 (`claude-3-haiku-20240307`)
* Claude Opus 3 (`claude-3-opus-20240229`)

### What can be batched

Any request that you can make to the Messages API can be included in a batch. This includes:

* Vision
* Tool use
* System messages
* Multi-turn conversations
* Any beta features

Since each request in the batch is processed independently, you can mix different types of requests within a single batch.

***

## Pricing

The Batches API offers significant cost savings. All usage is charged at 50% of the standard API prices.

| Model             | Batch input    | Batch output   |
| ----------------- | -------------- | -------------- |
| Claude Opus 4     | \$7.50 / MTok  | \$37.50 / MTok |
| Claude Sonnet 4   | \$1.50 / MTok  | \$7.50 / MTok  |
| Claude Sonnet 3.7 | \$1.50 / MTok  | \$7.50 / MTok  |
| Claude Sonnet 3.5 | \$1.50 / MTok  | \$7.50 / MTok  |
| Claude Haiku 3.5  | \$0.40 / MTok  | \$2 / MTok     |
| Claude Opus 3     | \$7.50 / MTok  | \$37.50 / MTok |
| Claude Haiku 3    | \$0.125 / MTok | \$0.625 / MTok |

***

## How to use the Message Batches API

### Prepare and create your batch

A Message Batch is composed of a list of requests to create a Message. The shape of an individual request is comprised of:

* A unique `custom_id` for identifying the Messages request
* A `params` object with the standard [Messages API](/en/api/messages) parameters

You can [create a batch](/en/api/creating-message-batches) by passing this list into the `requests` parameter:

<CodeGroup>
  ```bash Shell
  curl https://api.anthropic.com/v1/messages/batches \
       --header "x-api-key: $ANTHROPIC_API_KEY" \
       --header "anthropic-version: 2023-06-01" \
       --header "content-type: application/json" \
       --data \
  '{
      "requests": [
          {
              "custom_id": "my-first-request",
              "params": {
                  "model": "claude-opus-4-20250514",
                  "max_tokens": 1024,
                  "messages": [
                      {"role": "user", "content": "Hello, world"}
                  ]
              }
          },
          {
              "custom_id": "my-second-request",
              "params": {
                  "model": "claude-opus-4-20250514",
                  "max_tokens": 1024,
                  "messages": [
                      {"role": "user", "content": "Hi again, friend"}
                  ]
              }
          }
      ]
  }'
  ```

  ```python Python
  import anthropic
  from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
  from anthropic.types.messages.batch_create_params import Request

  client = anthropic.Anthropic()

  message_batch = client.messages.batches.create(
      requests=[
          Request(
              custom_id="my-first-request",
              params=MessageCreateParamsNonStreaming(
                  model="claude-opus-4-20250514",
                  max_tokens=1024,
                  messages=[{
                      "role": "user",
                      "content": "Hello, world",
                  }]
              )
          ),
          Request(
              custom_id="my-second-request",
              params=MessageCreateParamsNonStreaming(
                  model="claude-opus-4-20250514",
                  max_tokens=1024,
                  messages=[{
                      "role": "user",
                      "content": "Hi again, friend",
                  }]
              )
          )
      ]
  )

  print(message_batch)
  ```

  ```TypeScript TypeScript
  import Anthropic from '@anthropic-ai/sdk';

  const anthropic = new Anthropic();

  const messageBatch = await anthropic.messages.batches.create({
    requests: [{
      custom_id: "my-first-request",
      params: {
        model: "claude-opus-4-20250514",
        max_tokens: 1024,
        messages: [
          {"role": "user", "content": "Hello, world"}
        ]
      }
    }, {
      custom_id: "my-second-request",
      params: {
        model: "claude-opus-4-20250514",
        max_tokens: 1024,
        messages: [
          {"role": "user", "content": "Hi again, friend"}
        ]
      }
    }]
  });

  console.log(messageBatch)
  ```

  ```java Java
  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.Model;
  import com.anthropic.models.messages.batches.*;

  public class BatchExample {
      public static void main(String[] args) {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          BatchCreateParams params = BatchCreateParams.builder()
              .addRequest(BatchCreateParams.Request.builder()
                  .customId("my-first-request")
                  .params(BatchCreateParams.Request.Params.builder()
                      .model(Model.CLAUDE_OPUS_4_0)
                      .maxTokens(1024)
                      .addUserMessage("Hello, world")
                      .build())
                  .build())
              .addRequest(BatchCreateParams.Request.builder()
                  .customId("my-second-request")
                  .params(BatchCreateParams.Request.Params.builder()
                      .model(Model.CLAUDE_OPUS_4_0)
                      .maxTokens(1024)
                      .addUserMessage("Hi again, friend")
                      .build())
                  .build())
              .build();

          MessageBatch messageBatch = client.messages().batches().create(params);

          System.out.println(messageBatch);
      }
  }
  ```
</CodeGroup>

In this example, two separate requests are batched together for asynchronous processing. Each request has a unique `custom_id` and contains the standard parameters you'd use for a Messages API call.

<Tip>
  **Test your batch requests with the Messages API**

  Validation of the `params` object for each message request is performed asynchronously, and validation errors are returned when processing of the entire batch has ended. You can ensure that you are building your input correctly by verifying your request shape with the [Messages API](/en/api/messages) first.
</Tip>

When a batch is first created, the response will have a processing status of `in_progress`.

```JSON JSON
{
  "id": "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d",
  "type": "message_batch",
  "processing_status": "in_progress",
  "request_counts": {
    "processing": 2,
    "succeeded": 0,
    "errored": 0,
    "canceled": 0,
    "expired": 0
  },
  "ended_at": null,
  "created_at": "2024-09-24T18:37:24.100435Z",
  "expires_at": "2024-09-25T18:37:24.100435Z",
  "cancel_initiated_at": null,
  "results_url": null
}
```

### Tracking your batch

The Message Batch's `processing_status` field indicates the stage of processing the batch is in. It starts as `in_progress`, then updates to `ended` once all the requests in the batch have finished processing, and results are ready. You can monitor the state of your batch by visiting the [Console](https://console.anthropic.com/settings/workspaces/default/batches), or using the [retrieval endpoint](/en/api/retrieving-message-batches):

<CodeGroup>
  ```bash Shell
  curl https://api.anthropic.com/v1/messages/batches/msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d \
   --header "x-api-key: $ANTHROPIC_API_KEY" \
   --header "anthropic-version: 2023-06-01" \
   | sed -E 's/.*"id":"([^"]+)".*"processing_status":"([^"]+)".*/Batch \1 processing status is \2/'
  ```

  ```python Python
  import anthropic

  client = anthropic.Anthropic()

  message_batch = client.messages.batches.retrieve(
      "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d",
  )
  print(f"Batch {message_batch.id} processing status is {message_batch.processing_status}")
  ```

  ```TypeScript TypeScript
  import Anthropic from '@anthropic-ai/sdk';

  const anthropic = new Anthropic();

  const messageBatch = await anthropic.messages.batches.retrieve(
    "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d",
  );
  console.log(`Batch ${messageBatch.id} processing status is ${messageBatch.processing_status}`);
  ```

  ```java Java
  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.batches.*;

  public class BatchRetrieveExample {
      public static void main(String[] args) {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          MessageBatch messageBatch = client.messages().batches().retrieve(
                  BatchRetrieveParams.builder()
                          .messageBatchId("msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d")
                          .build()
          );
          System.out.printf("Batch %s processing status is %s%n",
                  messageBatch.id(), messageBatch.processingStatus());
      }
  }
  ```
</CodeGroup>

You can [poll](/en/api/messages-batch-examples#polling-for-message-batch-completion) this endpoint to know when processing has ended.

### Retrieving batch results

Once batch processing has ended, each Messages request in the batch will have a result. There are 4 result types:

| Result Type | Description                                                                                                                                                                 |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `succeeded` | Request was successful. Includes the message result.                                                                                                                        |
| `errored`   | Request encountered an error and a message was not created. Possible errors include invalid requests and internal server errors. You will not be billed for these requests. |
| `canceled`  | User canceled the batch before this request could be sent to the model. You will not be billed for these requests.                                                          |
| `expired`   | Batch reached its 24 hour expiration before this request could be sent to the model. You will not be billed for these requests.                                             |

You will see an overview of your results with the batch's `request_counts`, which shows how many requests reached each of these four states.

Results of the batch are available for download at the `results_url` property on the Message Batch, and if the organization permission allows, in the Console. Because of the potentially large size of the results, it's recommended to [stream results](/en/api/retrieving-message-batch-results) back rather than download them all at once.

<CodeGroup>
  ```bash Shell
  #!/bin/sh
  curl "https://api.anthropic.com/v1/messages/batches/msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d" \
    --header "anthropic-version: 2023-06-01" \
    --header "x-api-key: $ANTHROPIC_API_KEY" \
    | grep -o '"results_url":[[:space:]]*"[^"]*"' \
    | cut -d'"' -f4 \
    | while read -r url; do
      curl -s "$url" \
        --header "anthropic-version: 2023-06-01" \
        --header "x-api-key: $ANTHROPIC_API_KEY" \
        | sed 's/}{/}\n{/g' \
        | while IFS= read -r line
      do
        result_type=$(echo "$line" | sed -n 's/.*"result":[[:space:]]*{[[:space:]]*"type":[[:space:]]*"\([^"]*\)".*/\1/p')
        custom_id=$(echo "$line" | sed -n 's/.*"custom_id":[[:space:]]*"\([^"]*\)".*/\1/p')
        error_type=$(echo "$line" | sed -n 's/.*"error":[[:space:]]*{[[:space:]]*"type":[[:space:]]*"\([^"]*\)".*/\1/p')

        case "$result_type" in
          "succeeded")
            echo "Success! $custom_id"
            ;;
          "errored")
            if [ "$error_type" = "invalid_request" ]; then
              # Request body must be fixed before re-sending request
              echo "Validation error: $custom_id"
            else
              # Request can be retried directly
              echo "Server error: $custom_id"
            fi
            ;;
          "expired")
            echo "Expired: $line"
            ;;
        esac
      done
    done

  ```

  ```python Python
  import anthropic

  client = anthropic.Anthropic()

  # Stream results file in memory-efficient chunks, processing one at a time
  for result in client.messages.batches.results(
      "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d",
  ):
      match result.result.type:
          case "succeeded":
              print(f"Success! {result.custom_id}")
          case "errored":
              if result.result.error.type == "invalid_request":
                  # Request body must be fixed before re-sending request
                  print(f"Validation error {result.custom_id}")
              else:
                  # Request can be retried directly
                  print(f"Server error {result.custom_id}")
          case "expired":
              print(f"Request expired {result.custom_id}")
  ```

  ```TypeScript TypeScript
  import Anthropic from '@anthropic-ai/sdk';

  const anthropic = new Anthropic();

  // Stream results file in memory-efficient chunks, processing one at a time
  for await (const result of await anthropic.messages.batches.results(
      "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d"
  )) {
    switch (result.result.type) {
      case 'succeeded':
        console.log(`Success! ${result.custom_id}`);
        break;
      case 'errored':
        if (result.result.error.type == "invalid_request") {
          // Request body must be fixed before re-sending request
          console.log(`Validation error: ${result.custom_id}`);
        } else {
          // Request can be retried directly
          console.log(`Server error: ${result.custom_id}`);
        }
        break;
      case 'expired':
        console.log(`Request expired: ${result.custom_id}`);
        break;
    }
  }
  ```

  ```java Java
  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.core.http.StreamResponse;
  import com.anthropic.models.messages.batches.MessageBatchIndividualResponse;
  import com.anthropic.models.messages.batches.BatchResultsParams;

  public class BatchResultsExample {

      public static void main(String[] args) {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          // Stream results file in memory-efficient chunks, processing one at a time
          try (StreamResponse<MessageBatchIndividualResponse> streamResponse = client.messages()
                  .batches()
                  .resultsStreaming(
                          BatchResultsParams.builder()
                                  .messageBatchId("msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d")
                                  .build())) {

              streamResponse.stream().forEach(result -> {
                  if (result.result().isSucceeded()) {
                      System.out.println("Success! " + result.customId());
                  } else if (result.result().isErrored()) {
                      if (result.result().asErrored().error().error().isInvalidRequestError()) {
                          // Request body must be fixed before re-sending request
                          System.out.println("Validation error: " + result.customId());
                      } else {
                          // Request can be retried directly
                          System.out.println("Server error: " + result.customId());
                      }
                  } else if (result.result().isExpired()) {
                      System.out.println("Request expired: " + result.customId());
                  }
              });
          }
      }
  }
  ```
</CodeGroup>

The results will be in `.jsonl` format, where each line is a valid JSON object representing the result of a single request in the Message Batch. For each streamed result, you can do something different depending on its `custom_id` and result type. Here is an example set of results:

```JSON .jsonl file
{"custom_id":"my-second-request","result":{"type":"succeeded","message":{"id":"msg_014VwiXbi91y3JMjcpyGBHX5","type":"message","role":"assistant","model":"claude-opus-4-20250514","content":[{"type":"text","text":"Hello again! It's nice to see you. How can I assist you today? Is there anything specific you'd like to chat about or any questions you have?"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":11,"output_tokens":36}}}}
{"custom_id":"my-first-request","result":{"type":"succeeded","message":{"id":"msg_01FqfsLoHwgeFbguDgpz48m7","type":"message","role":"assistant","model":"claude-opus-4-20250514","content":[{"type":"text","text":"Hello! How can I assist you today? Feel free to ask me any questions or let me know if there's anything you'd like to chat about."}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":10,"output_tokens":34}}}}
```

If your result has an error, its `result.error` will be set to our standard [error shape](https://docs.anthropic.com/en/api/errors#error-shapes).

<Tip>
  **Batch results may not match input order**

  Batch results can be returned in any order, and may not match the ordering of requests when the batch was created. In the above example, the result for the second batch request is returned before the first. To correctly match results with their corresponding requests, always use the `custom_id` field.
</Tip>

### Using prompt caching with Message Batches

The Message Batches API supports prompt caching, allowing you to potentially reduce costs and processing time for batch requests. The pricing discounts from prompt caching and Message Batches can stack, providing even greater cost savings when both features are used together. However, since batch requests are processed asynchronously and concurrently, cache hits are provided on a best-effort basis. Users typically experience cache hit rates ranging from 30% to 98%, depending on their traffic patterns.

To maximize the likelihood of cache hits in your batch requests:

1. Include identical `cache_control` blocks in every Message request within your batch
2. Maintain a steady stream of requests to prevent cache entries from expiring after their 5-minute lifetime
3. Structure your requests to share as much cached content as possible

Example of implementing prompt caching in a batch:

<CodeGroup>
  ```bash Shell
  curl https://api.anthropic.com/v1/messages/batches \
       --header "x-api-key: $ANTHROPIC_API_KEY" \
       --header "anthropic-version: 2023-06-01" \
       --header "content-type: application/json" \
       --data \
  '{
      "requests": [
          {
              "custom_id": "my-first-request",
              "params": {
                  "model": "claude-opus-4-20250514",
                  "max_tokens": 1024,
                  "system": [
                      {
                          "type": "text",
                          "text": "You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n"
                      },
                      {
                          "type": "text",
                          "text": "<the entire contents of Pride and Prejudice>",
                          "cache_control": {"type": "ephemeral"}
                      }
                  ],
                  "messages": [
                      {"role": "user", "content": "Analyze the major themes in Pride and Prejudice."}
                  ]
              }
          },
          {
              "custom_id": "my-second-request",
              "params": {
                  "model": "claude-opus-4-20250514",
                  "max_tokens": 1024,
                  "system": [
                      {
                          "type": "text",
                          "text": "You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n"
                      },
                      {
                          "type": "text",
                          "text": "<the entire contents of Pride and Prejudice>",
                          "cache_control": {"type": "ephemeral"}
                      }
                  ],
                  "messages": [
                      {"role": "user", "content": "Write a summary of Pride and Prejudice."}
                  ]
              }
          }
      ]
  }'
  ```

  ```python Python
  import anthropic
  from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
  from anthropic.types.messages.batch_create_params import Request

  client = anthropic.Anthropic()

  message_batch = client.messages.batches.create(
      requests=[
          Request(
              custom_id="my-first-request",
              params=MessageCreateParamsNonStreaming(
                  model="claude-opus-4-20250514",
                  max_tokens=1024,
                  system=[
                      {
                          "type": "text",
                          "text": "You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n"
                      },
                      {
                          "type": "text",
                          "text": "<the entire contents of Pride and Prejudice>",
                          "cache_control": {"type": "ephemeral"}
                      }
                  ],
                  messages=[{
                      "role": "user",
                      "content": "Analyze the major themes in Pride and Prejudice."
                  }]
              )
          ),
          Request(
              custom_id="my-second-request",
              params=MessageCreateParamsNonStreaming(
                  model="claude-opus-4-20250514",
                  max_tokens=1024,
                  system=[
                      {
                          "type": "text",
                          "text": "You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n"
                      },
                      {
                          "type": "text",
                          "text": "<the entire contents of Pride and Prejudice>",
                          "cache_control": {"type": "ephemeral"}
                      }
                  ],
                  messages=[{
                      "role": "user",
                      "content": "Write a summary of Pride and Prejudice."
                  }]
              )
          )
      ]
  )
  ```

  ```typescript TypeScript
  import Anthropic from '@anthropic-ai/sdk';

  const anthropic = new Anthropic();

  const messageBatch = await anthropic.messages.batches.create({
    requests: [{
      custom_id: "my-first-request",
      params: {
        model: "claude-opus-4-20250514",
        max_tokens: 1024,
        system: [
          {
            type: "text",
            text: "You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n"
          },
          {
            type: "text",
            text: "<the entire contents of Pride and Prejudice>",
            cache_control: {type: "ephemeral"}
          }
        ],
        messages: [
          {"role": "user", "content": "Analyze the major themes in Pride and Prejudice."}
        ]
      }
    }, {
      custom_id: "my-second-request",
      params: {
        model: "claude-opus-4-20250514",
        max_tokens: 1024,
        system: [
          {
            type: "text",
            text: "You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n"
          },
          {
            type: "text",
            text: "<the entire contents of Pride and Prejudice>",
            cache_control: {type: "ephemeral"}
          }
        ],
        messages: [
          {"role": "user", "content": "Write a summary of Pride and Prejudice."}
        ]
      }
    }]
  });
  ```

  ```java Java
  import java.util.List;

  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.CacheControlEphemeral;
  import com.anthropic.models.messages.Model;
  import com.anthropic.models.messages.TextBlockParam;
  import com.anthropic.models.messages.batches.*;

  public class BatchExample {

      public static void main(String[] args) {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          BatchCreateParams createParams = BatchCreateParams.builder()
                  .addRequest(BatchCreateParams.Request.builder()
                          .customId("my-first-request")
                          .params(BatchCreateParams.Request.Params.builder()
                                  .model(Model.CLAUDE_OPUS_4_0)
                                  .maxTokens(1024)
                                  .systemOfTextBlockParams(List.of(
                                          TextBlockParam.builder()
                                                  .text("You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n")
                                                  .build(),
                                          TextBlockParam.builder()
                                                  .text("<the entire contents of Pride and Prejudice>")
                                                  .cacheControl(CacheControlEphemeral.builder().build())
                                                  .build()
                                  ))
                                  .addUserMessage("Analyze the major themes in Pride and Prejudice.")
                                  .build())
                          .build())
                  .addRequest(BatchCreateParams.Request.builder()
                          .customId("my-second-request")
                          .params(BatchCreateParams.Request.Params.builder()
                                  .model(Model.CLAUDE_OPUS_4_0)
                                  .maxTokens(1024)
                                  .systemOfTextBlockParams(List.of(
                                          TextBlockParam.builder()
                                                  .text("You are an AI assistant tasked with analyzing literary works. Your goal is to provide insightful commentary on themes, characters, and writing style.\n")
                                                  .build(),
                                          TextBlockParam.builder()
                                                  .text("<the entire contents of Pride and Prejudice>")
                                                  .cacheControl(CacheControlEphemeral.builder().build())
                                                  .build()
                                  ))
                                  .addUserMessage("Write a summary of Pride and Prejudice.")
                                  .build())
                          .build())
                  .build();

          MessageBatch messageBatch = client.messages().batches().create(createParams);
      }
  }
  ```
</CodeGroup>

In this example, both requests in the batch include identical system messages and the full text of Pride and Prejudice marked with `cache_control` to increase the likelihood of cache hits.

### Best practices for effective batching

To get the most out of the Batches API:

* Monitor batch processing status regularly and implement appropriate retry logic for failed requests.
* Use meaningful `custom_id` values to easily match results with requests, since order is not guaranteed.
* Consider breaking very large datasets into multiple batches for better manageability.
* Dry run a single request shape with the Messages API to avoid validation errors.

### Troubleshooting common issues

If experiencing unexpected behavior:

* Verify that the total batch request size doesn't exceed 256 MB. If the request size is too large, you may get a 413 `request_too_large` error.
* Check that you're using [supported models](#supported-models) for all requests in the batch.
* Ensure each request in the batch has a unique `custom_id`.
* Ensure that it has been less than 29 days since batch `created_at` (not processing `ended_at`) time. If over 29 days have passed, results will no longer be viewable.
* Confirm that the batch has not been canceled.

Note that the failure of one request in a batch does not affect the processing of other requests.

***

## Batch storage and privacy

* **Workspace isolation**: Batches are isolated within the Workspace they are created in. They can only be accessed by API keys associated with that Workspace, or users with permission to view Workspace batches in the Console.

* **Result availability**: Batch results are available for 29 days after the batch is created, allowing ample time for retrieval and processing.

***

## FAQ

<AccordionGroup>
  <Accordion title="How long does it take for a batch to process?">
    Batches may take up to 24 hours for processing, but many will finish sooner. Actual processing time depends on the size of the batch, current demand, and your request volume. It is possible for a batch to expire and not complete within 24 hours.
  </Accordion>

  <Accordion title="Is the Batches API available for all models?">
    See [above](#supported-models) for the list of supported models.
  </Accordion>

  <Accordion title="Can I use the Message Batches API with other API features?">
    Yes, the Message Batches API supports all features available in the Messages API, including beta features. However, streaming is not supported for batch requests.
  </Accordion>

  <Accordion title="How does the Message Batches API affect pricing?">
    The Message Batches API offers a 50% discount on all usage compared to standard API prices. This applies to input tokens, output tokens, and any special tokens. For more on pricing, visit our [pricing page](https://www.anthropic.com/pricing#anthropic-api).
  </Accordion>

  <Accordion title="Can I update a batch after it's been submitted?">
    No, once a batch has been submitted, it cannot be modified. If you need to make changes, you should cancel the current batch and submit a new one. Note that cancellation may not take immediate effect.
  </Accordion>

  <Accordion title="Are there Message Batches API rate limits and do they interact with the Messages API rate limits?">
    The Message Batches API has HTTP requests-based rate limits in addition to limits on the number of requests in need of processing. See [Message Batches API rate limits](/en/api/rate-limits#message-batches-api). Usage of the Batches API does not affect rate limits in the Messages API.
  </Accordion>

  <Accordion title="How do I handle errors in my batch requests?">
    When you retrieve the results, each request will have a `result` field indicating whether it `succeeded`, `errored`, was `canceled`, or `expired`. For `errored` results, additional error information will be provided. View the error response object in the [API reference](/en/api/creating-message-batches).
  </Accordion>

  <Accordion title="How does the Message Batches API handle privacy and data separation?">
    The Message Batches API is designed with strong privacy and data separation measures:

    1. Batches and their results are isolated within the Workspace in which they were created. This means they can only be accessed by API keys from that same Workspace.
    2. Each request within a batch is processed independently, with no data leakage between requests.
    3. Results are only available for a limited time (29 days), and follow our [data retention policy](https://support.anthropic.com/en/articles/7996866-how-long-do-you-store-personal-data).
    4. Downloading batch results in the Console can be disabled on the organization-level or on a per-workspace basis.
  </Accordion>

  <Accordion title="Can I use prompt caching in the Message Batches API?">
    Yes, it is possible to use prompt caching with Message Batches API. However, because asynchronous batch requests can be processed concurrently and in any order, cache hits are provided on a best-effort basis.
  </Accordion>
</AccordionGroup>

PDF API DOCS:

# PDF support

> Process PDFs with Claude. Extract text, analyze charts, and understand visual content from your documents.

You can now ask Claude about any text, pictures, charts, and tables in PDFs you provide. Some sample use cases:

* Analyzing financial reports and understanding charts/tables
* Extracting key information from legal documents
* Translation assistance for documents
* Converting document information into structured formats

## Before you begin

### Check PDF requirements

Claude works with any standard PDF. However, you should ensure your request size meets these requirements when using PDF support:

| Requirement               | Limit                                  |
| ------------------------- | -------------------------------------- |
| Maximum request size      | 32MB                                   |
| Maximum pages per request | 100                                    |
| Format                    | Standard PDF (no passwords/encryption) |

Please note that both limits are on the entire request payload, including any other content sent alongside PDFs.

Since PDF support relies on Claude's vision capabilities, it is subject to the same [limitations and considerations](/en/docs/build-with-claude/vision#limitations) as other vision tasks.

### Supported platforms and models

PDF support is currently supported via direct API access and Google Vertex AI on:

* Claude Opus 4 (`claude-opus-4-20250514`)
* Claude Sonnet 4 (`claude-sonnet-4-20250514`)
* Claude Sonnet 3.7 (`claude-3-7-sonnet-20250219`)
* Claude Sonnet 3.5 models (`claude-3-5-sonnet-20241022`, `claude-3-5-sonnet-20240620`)
* Claude Haiku 3.5 (`claude-3-5-haiku-20241022`)

PDF support is now available on Amazon Bedrock with the following considerations:

### Amazon Bedrock PDF Support

When using PDF support through Amazon Bedrock's Converse API, there are two distinct document processing modes:

<Note>
  **Important**: To access Claude's full visual PDF understanding capabilities in the Converse API, you must enable citations. Without citations enabled, the API falls back to basic text extraction only. Learn more about [working with citations](/en/docs/build-with-claude/citations).
</Note>

#### Document Processing Modes

1. **Converse Document Chat** (Original mode - Text extraction only)
   * Provides basic text extraction from PDFs
   * Cannot analyze images, charts, or visual layouts within PDFs
   * Uses approximately 1,000 tokens for a 3-page PDF
   * Automatically used when citations are not enabled

2. **Claude PDF Chat** (New mode - Full visual understanding)
   * Provides complete visual analysis of PDFs
   * Can understand and analyze charts, graphs, images, and visual layouts
   * Processes each page as both text and image for comprehensive understanding
   * Uses approximately 7,000 tokens for a 3-page PDF
   * **Requires citations to be enabled** in the Converse API

#### Key Limitations

* **Converse API**: Visual PDF analysis requires citations to be enabled. There is currently no option to use visual analysis without citations (unlike the InvokeModel API).
* **InvokeModel API**: Provides full control over PDF processing without forced citations.

#### Common Issues

If customers report that Claude isn't seeing images or charts in their PDFs when using the Converse API, they likely need to enable the citations flag. Without it, Converse falls back to basic text extraction only.

<Note>
  This is a known constraint with the Converse API that we're working to address. For applications that require visual PDF analysis without citations, consider using the InvokeModel API instead.
</Note>

<Note>
  For non-PDF files like .csv, .xlsx, .docx, .md, or .txt files, see [Working with other file formats](/en/docs/build-with-claude/files#working-with-other-file-formats).
</Note>

***

## Process PDFs with Claude

### Send your first PDF request

Let's start with a simple example using the Messages API. You can provide PDFs to Claude in three ways:

1. As a URL reference to a PDF hosted online
2. As a base64-encoded PDF in `document` content blocks
3. By a `file_id` from the [Files API](/en/docs/build-with-claude/files)

#### Option 1: URL-based PDF document

The simplest approach is to reference a PDF directly from a URL:

<CodeGroup>
  ```bash Shell
   curl https://api.anthropic.com/v1/messages \
     -H "content-type: application/json" \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -d '{
       "model": "claude-opus-4-20250514",
       "max_tokens": 1024,
       "messages": [{
           "role": "user",
           "content": [{
               "type": "document",
               "source": {
                   "type": "url",
                   "url": "https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf"
               }
           },
           {
               "type": "text",
               "text": "What are the key findings in this document?"
           }]
       }]
   }'
  ```

  ```Python Python
  import anthropic

  client = anthropic.Anthropic()
  message = client.messages.create(
      model="claude-opus-4-20250514",
      max_tokens=1024,
      messages=[
          {
              "role": "user",
              "content": [
                  {
                      "type": "document",
                      "source": {
                          "type": "url",
                          "url": "https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf"
                      }
                  },
                  {
                      "type": "text",
                      "text": "What are the key findings in this document?"
                  }
              ]
          }
      ],
  )

  print(message.content)
  ```

  ```TypeScript TypeScript
  import Anthropic from '@anthropic-ai/sdk';

  const anthropic = new Anthropic();

  async function main() {
    const response = await anthropic.messages.create({
      model: 'claude-opus-4-20250514',
      max_tokens: 1024,
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'document',
              source: {
                type: 'url',
                url: 'https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf',
              },
            },
            {
              type: 'text',
              text: 'What are the key findings in this document?',
            },
          ],
        },
      ],
    });
    
    console.log(response);
  }

  main();
  ```

  ```java Java
  import java.util.List;

  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.MessageCreateParams;
  import com.anthropic.models.messages.*;

  public class PdfExample {
      public static void main(String[] args) {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          // Create document block with URL
          DocumentBlockParam documentParam = DocumentBlockParam.builder()
                  .urlPdfSource("https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf")
                  .build();

          // Create a message with document and text content blocks
          MessageCreateParams params = MessageCreateParams.builder()
                  .model(Model.CLAUDE_OPUS_4_20250514)
                  .maxTokens(1024)
                  .addUserMessageOfBlockParams(
                          List.of(
                                  ContentBlockParam.ofDocument(documentParam),
                                  ContentBlockParam.ofText(
                                          TextBlockParam.builder()
                                                  .text("What are the key findings in this document?")
                                                  .build()
                                  )
                          )
                  )
                  .build();

          Message message = client.messages().create(params);
          System.out.println(message.content());
      }
  }
  ```
</CodeGroup>

#### Option 2: Base64-encoded PDF document

If you need to send PDFs from your local system or when a URL isn't available:

<CodeGroup>
  ```bash Shell
  # Method 1: Fetch and encode a remote PDF
  curl -s "https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf" | base64 | tr -d '\n' > pdf_base64.txt

  # Method 2: Encode a local PDF file
  # base64 document.pdf | tr -d '\n' > pdf_base64.txt

  # Create a JSON request file using the pdf_base64.txt content
  jq -n --rawfile PDF_BASE64 pdf_base64.txt '{
      "model": "claude-opus-4-20250514",
      "max_tokens": 1024,
      "messages": [{
          "role": "user",
          "content": [{
              "type": "document",
              "source": {
                  "type": "base64",
                  "media_type": "application/pdf",
                  "data": $PDF_BASE64
              }
          },
          {
              "type": "text",
              "text": "What are the key findings in this document?"
          }]
      }]
  }' > request.json

  # Send the API request using the JSON file
  curl https://api.anthropic.com/v1/messages \
    -H "content-type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d @request.json
  ```

  ```Python Python
  import anthropic
  import base64
  import httpx

  # First, load and encode the PDF 
  pdf_url = "https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf"
  pdf_data = base64.standard_b64encode(httpx.get(pdf_url).content).decode("utf-8")

  # Alternative: Load from a local file
  # with open("document.pdf", "rb") as f:
  #     pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

  # Send to Claude using base64 encoding
  client = anthropic.Anthropic()
  message = client.messages.create(
      model="claude-opus-4-20250514",
      max_tokens=1024,
      messages=[
          {
              "role": "user",
              "content": [
                  {
                      "type": "document",
                      "source": {
                          "type": "base64",
                          "media_type": "application/pdf",
                          "data": pdf_data
                      }
                  },
                  {
                      "type": "text",
                      "text": "What are the key findings in this document?"
                  }
              ]
          }
      ],
  )

  print(message.content)
  ```

  ```TypeScript TypeScript
  import Anthropic from '@anthropic-ai/sdk';
  import fetch from 'node-fetch';
  import fs from 'fs';

  async function main() {
    // Method 1: Fetch and encode a remote PDF
    const pdfURL = "https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf";
    const pdfResponse = await fetch(pdfURL);
    const arrayBuffer = await pdfResponse.arrayBuffer();
    const pdfBase64 = Buffer.from(arrayBuffer).toString('base64');
    
    // Method 2: Load from a local file
    // const pdfBase64 = fs.readFileSync('document.pdf').toString('base64');
    
    // Send the API request with base64-encoded PDF
    const anthropic = new Anthropic();
    const response = await anthropic.messages.create({
      model: 'claude-opus-4-20250514',
      max_tokens: 1024,
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'document',
              source: {
                type: 'base64',
                media_type: 'application/pdf',
                data: pdfBase64,
              },
            },
            {
              type: 'text',
              text: 'What are the key findings in this document?',
            },
          ],
        },
      ],
    });
    
    console.log(response);
  }

  main();
  ```

  ```java Java
  import java.io.IOException;
  import java.net.URI;
  import java.net.http.HttpClient;
  import java.net.http.HttpRequest;
  import java.net.http.HttpResponse;
  import java.util.Base64;
  import java.util.List;

  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.ContentBlockParam;
  import com.anthropic.models.messages.DocumentBlockParam;
  import com.anthropic.models.messages.Message;
  import com.anthropic.models.messages.MessageCreateParams;
  import com.anthropic.models.messages.Model;
  import com.anthropic.models.messages.TextBlockParam;

  public class PdfExample {
      public static void main(String[] args) throws IOException, InterruptedException {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          // Method 1: Download and encode a remote PDF
          String pdfUrl = "https://assets.anthropic.com/m/1cd9d098ac3e6467/original/Claude-3-Model-Card-October-Addendum.pdf";
          HttpClient httpClient = HttpClient.newHttpClient();
          HttpRequest request = HttpRequest.newBuilder()
                  .uri(URI.create(pdfUrl))
                  .GET()
                  .build();

          HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
          String pdfBase64 = Base64.getEncoder().encodeToString(response.body());

          // Method 2: Load from a local file
          // byte[] fileBytes = Files.readAllBytes(Path.of("document.pdf"));
          // String pdfBase64 = Base64.getEncoder().encodeToString(fileBytes);

          // Create document block with base64 data
          DocumentBlockParam documentParam = DocumentBlockParam.builder()
                  .base64PdfSource(pdfBase64)
                  .build();

          // Create a message with document and text content blocks
          MessageCreateParams params = MessageCreateParams.builder()
                  .model(Model.CLAUDE_OPUS_4_20250514)
                  .maxTokens(1024)
                  .addUserMessageOfBlockParams(
                          List.of(
                                  ContentBlockParam.ofDocument(documentParam),
                                  ContentBlockParam.ofText(TextBlockParam.builder().text("What are the key findings in this document?").build())
                          )
                  )
                  .build();

          Message message = client.messages().create(params);
          message.content().stream()
                  .flatMap(contentBlock -> contentBlock.text().stream())
                  .forEach(textBlock -> System.out.println(textBlock.text()));
      }
  }
  ```
</CodeGroup>

#### Option 3: Files API

For PDFs you'll use repeatedly, or when you want to avoid encoding overhead, use the [Files API](/en/docs/build-with-claude/files):

<CodeGroup>
  ```bash Shell
  # First, upload your PDF to the Files API
  curl -X POST https://api.anthropic.com/v1/files \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "anthropic-beta: files-api-2025-04-14" \
    -F "file=@document.pdf"

  # Then use the returned file_id in your message
  curl https://api.anthropic.com/v1/messages \
    -H "content-type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "anthropic-beta: files-api-2025-04-14" \
    -d '{
      "model": "claude-opus-4-20250514", 
      "max_tokens": 1024,
      "messages": [{
        "role": "user",
        "content": [{
          "type": "document",
          "source": {
            "type": "file",
            "file_id": "file_abc123"
          }
        },
        {
          "type": "text",
          "text": "What are the key findings in this document?"
        }]
      }]
    }'
  ```

  ```python Python
  import anthropic

  client = anthropic.Anthropic()

  # Upload the PDF file
  with open("document.pdf", "rb") as f:
      file_upload = client.beta.files.upload(file=("document.pdf", f, "application/pdf"))

  # Use the uploaded file in a message
  message = client.beta.messages.create(
      model="claude-opus-4-20250514",
      max_tokens=1024,
      betas=["files-api-2025-04-14"],
      messages=[
          {
              "role": "user",
              "content": [
                  {
                      "type": "document",
                      "source": {
                          "type": "file",
                          "file_id": file_upload.id
                      }
                  },
                  {
                      "type": "text",
                      "text": "What are the key findings in this document?"
                  }
              ]
          }
      ],
  )

  print(message.content)
  ```

  ```typescript TypeScript
  import { Anthropic, toFile } from '@anthropic-ai/sdk';
  import fs from 'fs';

  const anthropic = new Anthropic();

  async function main() {
    // Upload the PDF file
    const fileUpload = await anthropic.beta.files.upload({
      file: toFile(fs.createReadStream('document.pdf'), undefined, { type: 'application/pdf' })
    }, {
      betas: ['files-api-2025-04-14']
    });

    // Use the uploaded file in a message
    const response = await anthropic.beta.messages.create({
      model: 'claude-opus-4-20250514',
      max_tokens: 1024,
      betas: ['files-api-2025-04-14'],
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'document',
              source: {
                type: 'file',
                file_id: fileUpload.id
              }
            },
            {
              type: 'text',
              text: 'What are the key findings in this document?'
            }
          ]
        }
      ]
    });

    console.log(response);
  }

  main();
  ```

  ```java Java
  import java.io.IOException;
  import java.nio.file.Files;
  import java.nio.file.Path;
  import java.util.List;

  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.File;
  import com.anthropic.models.files.FileUploadParams;
  import com.anthropic.models.messages.*;

  public class PdfFilesExample {
      public static void main(String[] args) throws IOException {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          // Upload the PDF file
          File file = client.beta().files().upload(FileUploadParams.builder()
                  .file(Files.newInputStream(Path.of("document.pdf")))
                  .build());

          // Use the uploaded file in a message
          DocumentBlockParam documentParam = DocumentBlockParam.builder()
                  .fileSource(file.id())
                  .build();

          MessageCreateParams params = MessageCreateParams.builder()
                  .model(Model.CLAUDE_OPUS_4_20250514)
                  .maxTokens(1024)
                  .addUserMessageOfBlockParams(
                          List.of(
                                  ContentBlockParam.ofDocument(documentParam),
                                  ContentBlockParam.ofText(
                                          TextBlockParam.builder()
                                                  .text("What are the key findings in this document?")
                                                  .build()
                                  )
                          )
                  )
                  .build();

          Message message = client.messages().create(params);
          System.out.println(message.content());
      }
  }
  ```
</CodeGroup>

### How PDF support works

When you send a PDF to Claude, the following steps occur:

<Steps>
  <Step title="The system extracts the contents of the document.">
    * The system converts each page of the document into an image.
    * The text from each page is extracted and provided alongside each page's image.
  </Step>

  <Step title="Claude analyzes both the text and images to better understand the document.">
    * Documents are provided as a combination of text and images for analysis.
    * This allows users to ask for insights on visual elements of a PDF, such as charts, diagrams, and other non-textual content.
  </Step>

  <Step title="Claude responds, referencing the PDF's contents if relevant.">
    Claude can reference both textual and visual content when it responds. You can further improve performance by integrating PDF support with:

    * **Prompt caching**: To improve performance for repeated analysis.
    * **Batch processing**: For high-volume document processing.
    * **Tool use**: To extract specific information from documents for use as tool inputs.
  </Step>
</Steps>

### Estimate your costs

The token count of a PDF file depends on the total text extracted from the document as well as the number of pages:

* Text token costs: Each page typically uses 1,500-3,000 tokens per page depending on content density. Standard API pricing applies with no additional PDF fees.
* Image token costs: Since each page is converted into an image, the same [image-based cost calculations](/en/docs/build-with-claude/vision#evaluate-image-size) are applied.

You can use [token counting](/en/docs/build-with-claude/token-counting) to estimate costs for your specific PDFs.

***

## Optimize PDF processing

### Improve performance

Follow these best practices for optimal results:

* Place PDFs before text in your requests
* Use standard fonts
* Ensure text is clear and legible
* Rotate pages to proper upright orientation
* Use logical page numbers (from PDF viewer) in prompts
* Split large PDFs into chunks when needed
* Enable prompt caching for repeated analysis

### Scale your implementation

For high-volume processing, consider these approaches:

#### Use prompt caching

Cache PDFs to improve performance on repeated queries:

<CodeGroup>
  ```bash Shell
  # Create a JSON request file using the pdf_base64.txt content
  jq -n --rawfile PDF_BASE64 pdf_base64.txt '{
      "model": "claude-opus-4-20250514",
      "max_tokens": 1024,
      "messages": [{
          "role": "user",
          "content": [{
              "type": "document",
              "source": {
                  "type": "base64",
                  "media_type": "application/pdf",
                  "data": $PDF_BASE64
              },
              "cache_control": {
                "type": "ephemeral"
              }
          },
          {
              "type": "text",
              "text": "Which model has the highest human preference win rates across each use-case?"
          }]
      }]
  }' > request.json

  # Then make the API call using the JSON file
  curl https://api.anthropic.com/v1/messages \
    -H "content-type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d @request.json
  ```

  ```python Python
  message = client.messages.create(
      model="claude-opus-4-20250514",
      max_tokens=1024,
      messages=[
          {
              "role": "user",
              "content": [
                  {
                      "type": "document",
                      "source": {
                          "type": "base64",
                          "media_type": "application/pdf",
                          "data": pdf_data
                      },
                      "cache_control": {"type": "ephemeral"}
                  },
                  {
                      "type": "text",
                      "text": "Analyze this document."
                  }
              ]
          }
      ],
  )
  ```

  ```TypeScript TypeScript
  const response = await anthropic.messages.create({
    model: 'claude-opus-4-20250514',
    max_tokens: 1024,
    messages: [
      {
        content: [
          {
            type: 'document',
            source: {
              media_type: 'application/pdf',
              type: 'base64',
              data: pdfBase64,
            },
            cache_control: { type: 'ephemeral' },
          },
          {
            type: 'text',
            text: 'Which model has the highest human preference win rates across each use-case?',
          },
        ],
        role: 'user',
      },
    ],
  });
  console.log(response);
  ```

  ```java Java
  import java.io.IOException;
  import java.nio.file.Files;
  import java.nio.file.Paths;
  import java.util.List;

  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.Base64PdfSource;
  import com.anthropic.models.messages.CacheControlEphemeral;
  import com.anthropic.models.messages.ContentBlockParam;
  import com.anthropic.models.messages.DocumentBlockParam;
  import com.anthropic.models.messages.Message;
  import com.anthropic.models.messages.MessageCreateParams;
  import com.anthropic.models.messages.Model;
  import com.anthropic.models.messages.TextBlockParam;

  public class MessagesDocumentExample {

      public static void main(String[] args) throws IOException {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          // Read PDF file as base64
          byte[] pdfBytes = Files.readAllBytes(Paths.get("pdf_base64.txt"));
          String pdfBase64 = new String(pdfBytes);

          MessageCreateParams params = MessageCreateParams.builder()
                  .model(Model.CLAUDE_OPUS_4_20250514)
                  .maxTokens(1024)
                  .addUserMessageOfBlockParams(List.of(
                          ContentBlockParam.ofDocument(
                                  DocumentBlockParam.builder()
                                          .source(Base64PdfSource.builder()
                                                  .data(pdfBase64)
                                                  .build())
                                          .cacheControl(CacheControlEphemeral.builder().build())
                                          .build()),
                          ContentBlockParam.ofText(
                                  TextBlockParam.builder()
                                          .text("Which model has the highest human preference win rates across each use-case?")
                                          .build())
                  ))
                  .build();


          Message message = client.messages().create(params);
          System.out.println(message);
      }
  }
  ```
</CodeGroup>

#### Process document batches

Use the Message Batches API for high-volume workflows:

<CodeGroup>
  ```bash Shell
  # Create a JSON request file using the pdf_base64.txt content
  jq -n --rawfile PDF_BASE64 pdf_base64.txt '
  {
    "requests": [
        {
            "custom_id": "my-first-request",
            "params": {
                "model": "claude-opus-4-20250514",
                "max_tokens": 1024,
                "messages": [
                  {
                      "role": "user",
                      "content": [
                          {
                              "type": "document",
                              "source": {
                                  "type": "base64",
                                  "media_type": "application/pdf",
                                  "data": $PDF_BASE64
                              }
                          },
                          {
                              "type": "text",
                              "text": "Which model has the highest human preference win rates across each use-case?"
                          }
                      ]
                  }
                ]
            }
        },
        {
            "custom_id": "my-second-request",
            "params": {
                "model": "claude-opus-4-20250514",
                "max_tokens": 1024,
                "messages": [
                  {
                      "role": "user",
                      "content": [
                          {
                              "type": "document",
                              "source": {
                                  "type": "base64",
                                  "media_type": "application/pdf",
                                  "data": $PDF_BASE64
                              }
                          },
                          {
                              "type": "text",
                              "text": "Extract 5 key insights from this document."
                          }
                      ]
                  }
                ]
            }
        }
    ]
  }
  ' > request.json

  # Then make the API call using the JSON file
  curl https://api.anthropic.com/v1/messages/batches \
    -H "content-type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d @request.json
  ```

  ```python Python
  message_batch = client.messages.batches.create(
      requests=[
          {
              "custom_id": "doc1",
              "params": {
                  "model": "claude-opus-4-20250514",
                  "max_tokens": 1024,
                  "messages": [
                      {
                          "role": "user",
                          "content": [
                              {
                                  "type": "document",
                                  "source": {
                                      "type": "base64",
                                      "media_type": "application/pdf",
                                      "data": pdf_data
                                  }
                              },
                              {
                                  "type": "text",
                                  "text": "Summarize this document."
                              }
                          ]
                      }
                  ]
              }
          }
      ]
  )
  ```

  ```TypeScript TypeScript
  const response = await anthropic.messages.batches.create({
    requests: [
      {
        custom_id: 'my-first-request',
        params: {
          max_tokens: 1024,
          messages: [
            {
              content: [
                {
                  type: 'document',
                  source: {
                    media_type: 'application/pdf',
                    type: 'base64',
                    data: pdfBase64,
                  },
                },
                {
                  type: 'text',
                  text: 'Which model has the highest human preference win rates across each use-case?',
                },
              ],
              role: 'user',
            },
          ],
          model: 'claude-opus-4-20250514',
        },
      },
      {
        custom_id: 'my-second-request',
        params: {
          max_tokens: 1024,
          messages: [
            {
              content: [
                {
                  type: 'document',
                  source: {
                    media_type: 'application/pdf',
                    type: 'base64',
                    data: pdfBase64,
                  },
                },
                {
                  type: 'text',
                  text: 'Extract 5 key insights from this document.',
                },
              ],
              role: 'user',
            },
          ],
          model: 'claude-opus-4-20250514',
        },
      }
    ],
  });
  console.log(response);
  ```

  ```java Java
  import java.io.IOException;
  import java.nio.file.Files;
  import java.nio.file.Paths;
  import java.util.List;

  import com.anthropic.client.AnthropicClient;
  import com.anthropic.client.okhttp.AnthropicOkHttpClient;
  import com.anthropic.models.messages.*;
  import com.anthropic.models.messages.batches.*;

  public class MessagesBatchDocumentExample {

      public static void main(String[] args) throws IOException {
          AnthropicClient client = AnthropicOkHttpClient.fromEnv();

          // Read PDF file as base64
          byte[] pdfBytes = Files.readAllBytes(Paths.get("pdf_base64.txt"));
          String pdfBase64 = new String(pdfBytes);

          BatchCreateParams params = BatchCreateParams.builder()
                  .addRequest(BatchCreateParams.Request.builder()
                          .customId("my-first-request")
                          .params(BatchCreateParams.Request.Params.builder()
                                  .model(Model.CLAUDE_OPUS_4_20250514)
                                  .maxTokens(1024)
                                  .addUserMessageOfBlockParams(List.of(
                                          ContentBlockParam.ofDocument(
                                                  DocumentBlockParam.builder()
                                                          .source(Base64PdfSource.builder()
                                                                  .data(pdfBase64)
                                                                  .build())
                                                          .build()
                                          ),
                                          ContentBlockParam.ofText(
                                                  TextBlockParam.builder()
                                                          .text("Which model has the highest human preference win rates across each use-case?")
                                                          .build()
                                          )
                                  ))
                                  .build())
                          .build())
                  .addRequest(BatchCreateParams.Request.builder()
                          .customId("my-second-request")
                          .params(BatchCreateParams.Request.Params.builder()
                                  .model(Model.CLAUDE_OPUS_4_20250514)
                                  .maxTokens(1024)
                                  .addUserMessageOfBlockParams(List.of(
                                          ContentBlockParam.ofDocument(
                                          DocumentBlockParam.builder()
                                                  .source(Base64PdfSource.builder()
                                                          .data(pdfBase64)
                                                          .build())
                                                  .build()
                                          ),
                                          ContentBlockParam.ofText(
                                                  TextBlockParam.builder()
                                                          .text("Extract 5 key insights from this document.")
                                                          .build()
                                          )
                                  ))
                                  .build())
                          .build())
                  .build();

          MessageBatch batch = client.messages().batches().create(params);
          System.out.println(batch);
      }
  }
  ```
</CodeGroup>

## Next steps

<CardGroup cols={2}>
  <Card title="Try PDF examples" icon="file-pdf" href="https://github.com/anthropics/anthropic-cookbook/tree/main/multimodal">
    Explore practical examples of PDF processing in our cookbook recipe.
  </Card>

  <Card title="View API reference" icon="code" href="/en/api/messages">
    See complete API documentation for PDF support.
  </Card>
</CardGroup>
