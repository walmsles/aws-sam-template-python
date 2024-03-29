# aws-sam-template-python

Congratulations, you have just created a Serverless "Hello World" application using the AWS Serverless Application Model (AWS SAM) for the `pythoon3.9` runtime, and options to bootstrap it with [**AWS Lambda Powertools for TypeScript**](https://awslabs.github.io/aws-lambda-powertools-typescript/latest/) (Lambda Powertools) utilities for Logging, Tracing and Metrics.

Powertools is a developer toolkit to implement Serverless best practices and increase developer velocity.

## Powertools features

Powertools provides three core utilities:

* **[Tracing](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/tracer/)** - Decorators and utilities to trace Lambda function handlers, and both synchronous and asynchronous functions
* **[Logging](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/logger/)** - Structured logging made easier, and decorator to enrich structured logging with key Lambda context details
* **[Metrics](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/metrics/)** - Custom Metrics created asynchronously via CloudWatch Embedded Metric Format (EMF)

Find the complete project's [documentation here](https://awslabs.github.io/aws-lambda-powertools-python).

### Installing AWS Lambda Powertools for Python

With [pip](https://pip.pypa.io/en/latest/index.html) installed, run:

```bash
make dev
poetry add "aws-lambda-powertools[tracer]"
```

This project template uses `poetry` for dependency management and enables every lambda service to have its own defined Python dependencies to ensure each lambda has the smallest possible package footprint.  Specific service level Python dependencies are added using `poetry add <dependency> --group <service_name>` where `dependency` is the required library and `service_name` is the folder under `services` which contains the lambda function.  Any centrally installed dependencies will be included, for example aws-lambda-powertools installed above will ensure **all lambda services** have aws-lambda-powertools in their requirements.txt file.

the `requirements.txt` files are not managed in git and will be ignored since the files are generated through the `make deps` command which runs the `scripts/make-deps.sh` script.

### Powertools Examples

* [Tutorial](https://awslabs.github.io/aws-lambda-powertools-python/latest/tutorial)
* [Serverless Shopping cart](https://github.com/aws-samples/aws-serverless-shopping-cart)
* [Serverless Airline](https://github.com/aws-samples/aws-serverless-airline-booking)
* [Serverless E-commerce platform](https://github.com/aws-samples/aws-serverless-ecommerce-platform)
* [Serverless GraphQL Nanny Booking Api](https://github.com/trey-rosius/babysitter_api)

## Working with this project

This project contains source code and supporting files for a serverless application that you can deploy with the SAM CLI. It includes the following files and folders.

* services - main folder where all your lambda services are created.
* services/hello_world - Code for the application's hello_world Lambda function.
* events - Invocation events that you can use to invoke the function.
* tests - Unit tests for the application code.
* template.yaml - A template that defines the application's AWS resources.

The application uses several AWS resources, including Lambda functions and an API Gateway API. These resources are defined in the `template.yaml` file in this project. You can update the template to add AWS resources through the same deployment process that updates your application code.

If you prefer to use an integrated development environment (IDE) to build and test your application, you can use the AWS Toolkit.
The AWS Toolkit is an open source plug-in for popular IDEs that uses the SAM CLI to build and deploy serverless applications on AWS. The AWS Toolkit also adds a simplified step-through debugging experience for Lambda function code. See the following links to get started.

* [CLion](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [GoLand](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [IntelliJ](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [WebStorm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [Rider](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [PhpStorm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [PyCharm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [RubyMine](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [DataGrip](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
* [VS Code](https://docs.aws.amazon.com/toolkit-for-vscode/latest/userguide/welcome.html)
* [Visual Studio](https://docs.aws.amazon.com/toolkit-for-visual-studio/latest/user-guide/welcome.html)

### Adding New Dependencies

The core tenets of this project are reasonably simple:

1. Manage all Python dependencies using a single tool (Poetry)
2. Manage all dependencies centrally in a Python virtual environment so IDE type hinting just works without any laborious or continuous tweaking of IDE settings.
3. Enable Lambda functions to have specific dependencies so that only required dependencies are installed (no unused dependencies in the Lambda package).  This ensures each Lambda package is as small as possible which is essential for managing cold start times.
4. No editing of **requirements.txt** for any Lambda sub-folder (requirements.txt for Lambda functions are always generated).

The most important tenet is the last one - making sure Lambda functions only have the dependencies they need.  To achieve this we use Poetry's **group** feature, which enables custom dependency groups to exist.  The expectation is that the **services** sub-folders contain each Lambda function (required for SAM build) and each sub-folder represents a dependency group for **Poetry**.

For example, if you wanted to install the **tenacity** library into the **hello_world** service (Lambda function), you would run the following command:  `poetry add tenacity --group hello_world`.  This will add **tenacity** to the dependency group for the **hello_world** service.  If we had multiple services only **hello_world** will have the **tenacity** dependency added to its requirements.txt generated file.

For adding common dependencies for all Lambda functions you can go ahead and do `poetry add "aws-lambda-powertools[tracer]"`.  All **main** dependencies added in this way will also be included in the generated requirements.txt file for all Lambda functions.

The magic of creating and managing the dependencies is all done within the `scripts/make-deps.sh` bash script which iterates over the **services** sub-folders and does an export of poetry dependencies for the specific **group** (if it exists) and also **main**.  It does also force some folder structure requirements on you for the project - but I feel that is okay, because currently Lambda folders for SAM Cli example projects are all over the place anyway - so some opinionated structure is always helpful!

### Deploy the sample application

The Serverless Application Model Command Line Interface (SAM CLI) is an extension of the AWS CLI that adds functionality for building and testing Lambda applications. It uses Docker to run your functions in an Amazon Linux environment that matches Lambda. It can also emulate your application's build environment and API.

To use the SAM CLI, you need the following tools.

* SAM CLI - [Install the SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
* [Python 3 installed](https://www.python.org/downloads/)
* Docker - [Install Docker community edition](https://hub.docker.com/search/?type=edition&offering=community)

To build and deploy your application for the first time, run the following in your shell:

```bash
make guided
```

This command will build the source of your application followed by packaging and deploying your application to AWS, with a series of prompts:

* **Stack Name**: The name of the stack to deploy to CloudFormation. This should be unique to your account and region, and a good starting point would be something matching your project name.
* **AWS Region**: The AWS region you want to deploy your app to.
* **Confirm changes before deploy**: If set to yes, any change sets will be shown to you before execution for manual review. If set to no, the AWS SAM CLI will automatically deploy application changes.
* **Allow SAM CLI IAM role creation**: Many AWS SAM templates, including this example, create AWS IAM roles required for the AWS Lambda function(s) included to access AWS services. By default, these are scoped down to minimum required permissions. To deploy an AWS CloudFormation stack which creates or modifies IAM roles, the `CAPABILITY_IAM` value for `capabilities` must be provided. If permission isn't provided through this prompt, to deploy this example you must explicitly pass `--capabilities CAPABILITY_IAM` to the `sam deploy` command.
* **Save arguments to samconfig.toml**: If set to yes, your choices will be saved to a configuration file inside the project, so that in the future you can just re-run `sam deploy` without parameters to deploy changes to your application.

You can find your API Gateway Endpoint URL in the output values displayed after deployment.

### Use the SAM CLI to build and test locally

Build your application with the `make build` command.

```bash
make build
```

The SAM CLI installs dependencies defined in `services/hello_world/requirements.txt`, creates a deployment package, and saves it in the `.aws-sam/build` folder.  The `requirements.txt` file is generated during the `make build` process based on dependencies installed in your local Python virtual environment with `poetry`.

Test a single function by invoking it directly with a test event. An event is a JSON document that represents the input that the function receives from the event source. Test events are included in the `events` folder in this project.

Run functions locally and invoke them with the `sam local invoke` command.

```bash
aws-sam-template-python$ sam local invoke HelloWorldFunction --event events/hello.json
```

The SAM CLI can also emulate your application's API. Use the `sam local start-api` to run the API locally on port 3000.

```bash
aws-sam-template-python$ sam local start-api
aws-sam-template-python$ curl http://localhost:3000/
```

The SAM CLI reads the application template to determine the API's routes and the functions that they invoke. The `Events` property on each function's definition includes the route and method for each path.

```yaml
      Events:
        HelloWorld:
          Type: Api
          Properties:
            Path: /hello
            Method: get
```

### Add a resource to your application

The application template uses AWS Serverless Application Model (AWS SAM) to define application resources. AWS SAM is an extension of AWS CloudFormation with a simpler syntax for configuring common serverless application resources such as functions, triggers, and APIs. For resources not included in [the SAM specification](https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md), you can use standard [AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html) resource types.

### Fetch, tail, and filter Lambda function logs

To simplify troubleshooting, SAM CLI has a command called `sam logs`. `sam logs` lets you fetch logs generated by your deployed Lambda function from the command line. In addition to printing the logs on the terminal, this command has several nifty features to help you quickly find the bug.

`NOTE`: This command works for all AWS Lambda functions; not just the ones you deploy using SAM.

```bash
aws-sam-template-python$ sam logs -n HelloWorldFunction --stack-name aws-sam-template-python --tail
```

You can find more information and examples about filtering Lambda function logs in the [SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html).

### Tests

Tests are defined in the `tests` folder in this project. Use PIP to install the test dependencies and run tests.

```bash
aws-sam-template-python$ pip install -r tests/requirements.txt --user
# unit test
aws-sam-template-python$ python -m pytest tests/unit -v
# integration test, requiring deploying the stack first.
# Create the env variable AWS_SAM_STACK_NAME with the name of the stack we are testing
aws-sam-template-python$ AWS_SAM_STACK_NAME=<stack-name> python -m pytest tests/integration -v
```

### Cleanup

To delete the sample application that you created, use the AWS CLI. Assuming you used your project name for the stack name, you can run the following:

```bash
sam delete --stack-name aws-sam-template-python
```

## Resources

See the [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) for an introduction to SAM specification, the SAM CLI, and serverless application concepts.

Next, you can use AWS Serverless Application Repository to deploy ready to use Apps that go beyond hello world samples and learn how authors developed their applications: [AWS Serverless Application Repository main page](https://aws.amazon.com/serverless/serverlessrepo/)
