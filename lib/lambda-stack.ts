import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface LambdaStackProps extends cdk.StackProps {
  /** S3 bucket for report storage */
  groundTruthBucket: s3.IBucket;
}

/**
 * LambdaStack — Phase 1b
 *
 * Provisions all Lambda "tool" functions used by agents:
 *   - fetch_news: Fetches news headlines from RSS feeds
 *   - fetch_rss: Generic RSS/Atom feed parser
 *   - fetch_github: Fetches GitHub repo activity
 *   - write_report: Writes analysis reports to S3
 *
 * Each function has least-privilege IAM and structured logging.
 */
export class LambdaStack extends cdk.Stack {
  public readonly fetchNewsFunction: lambda.Function;
  public readonly fetchRssFunction: lambda.Function;
  public readonly fetchGithubFunction: lambda.Function;
  public readonly writeReportFunction: lambda.Function;

  /** All Lambda function ARNs for agent action groups */
  public readonly functionArns: { [key: string]: string };

  constructor(scope: Construct, id: string, props: LambdaStackProps) {
    super(scope, id, props);

    const pythonRuntime = lambda.Runtime.PYTHON_3_12;
    const defaultTimeout = cdk.Duration.seconds(30);
    const defaultMemory = 256;
    const logRetention = logs.RetentionDays.TWO_WEEKS;

    // ─── fetch_news Lambda ────────────────────────────────────────────
    this.fetchNewsFunction = new lambda.Function(this, 'FetchNewsFunction', {
      functionName: 'aegis-fetch-news',
      description: 'Fetches latest news headlines from RSS news feeds',
      runtime: pythonRuntime,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('./lambda/fetch_news'),
      timeout: defaultTimeout,
      memorySize: defaultMemory,
      environment: {
        MAX_ARTICLES: '15',
        LOG_LEVEL: 'INFO',
      },
      logGroup: new logs.LogGroup(this, 'FetchNewsLogGroup', {
        logGroupName: '/aegis-tactical/lambda/fetch-news',
        retention: logRetention,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // ─── fetch_rss Lambda ─────────────────────────────────────────────
    this.fetchRssFunction = new lambda.Function(this, 'FetchRssFunction', {
      functionName: 'aegis-fetch-rss',
      description: 'Parses RSS/Atom feeds from configurable URLs',
      runtime: pythonRuntime,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('./lambda/fetch_rss'),
      timeout: defaultTimeout,
      memorySize: defaultMemory,
      environment: {
        MAX_ENTRIES: '20',
        LOG_LEVEL: 'INFO',
      },
      logGroup: new logs.LogGroup(this, 'FetchRssLogGroup', {
        logGroupName: '/aegis-tactical/lambda/fetch-rss',
        retention: logRetention,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // ─── fetch_github Lambda ──────────────────────────────────────────
    this.fetchGithubFunction = new lambda.Function(this, 'FetchGithubFunction', {
      functionName: 'aegis-fetch-github',
      description: 'Fetches recent commits and events from GitHub repositories',
      runtime: pythonRuntime,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('./lambda/fetch_github'),
      timeout: defaultTimeout,
      memorySize: defaultMemory,
      environment: {
        MAX_RESULTS: '20',
        GITHUB_TOKEN: '',  // Set via SSM or Secrets Manager in production
        LOG_LEVEL: 'INFO',
      },
      logGroup: new logs.LogGroup(this, 'FetchGithubLogGroup', {
        logGroupName: '/aegis-tactical/lambda/fetch-github',
        retention: logRetention,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // ─── write_report Lambda ──────────────────────────────────────────
    this.writeReportFunction = new lambda.Function(this, 'WriteReportFunction', {
      functionName: 'aegis-write-report',
      description: 'Writes structured analysis reports to S3 as Markdown + JSON',
      runtime: pythonRuntime,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('./lambda/write_report'),
      timeout: defaultTimeout,
      memorySize: defaultMemory,
      environment: {
        REPORT_BUCKET: props.groundTruthBucket.bucketName,
        REPORT_PREFIX: 'reports/',
        LOG_LEVEL: 'INFO',
      },
      logGroup: new logs.LogGroup(this, 'WriteReportLogGroup', {
        logGroupName: '/aegis-tactical/lambda/write-report',
        retention: logRetention,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // Grant write_report permission to write to S3
    props.groundTruthBucket.grantWrite(this.writeReportFunction, 'reports/*');

    // ─── Collect ARNs for agent action groups ─────────────────────────
    this.functionArns = {
      fetchNews: this.fetchNewsFunction.functionArn,
      fetchRss: this.fetchRssFunction.functionArn,
      fetchGithub: this.fetchGithubFunction.functionArn,
      writeReport: this.writeReportFunction.functionArn,
    };

    // ─── Outputs ──────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'FetchNewsFunctionArn', {
      value: this.fetchNewsFunction.functionArn,
      exportName: 'AegisFetchNewsArn',
    });

    new cdk.CfnOutput(this, 'FetchRssFunctionArn', {
      value: this.fetchRssFunction.functionArn,
      exportName: 'AegisFetchRssArn',
    });

    new cdk.CfnOutput(this, 'FetchGithubFunctionArn', {
      value: this.fetchGithubFunction.functionArn,
      exportName: 'AegisFetchGithubArn',
    });

    new cdk.CfnOutput(this, 'WriteReportFunctionArn', {
      value: this.writeReportFunction.functionArn,
      exportName: 'AegisWriteReportArn',
    });
  }
}
