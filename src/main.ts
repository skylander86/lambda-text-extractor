import { App, Duration, Stack, } from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as path from "path";

const app = new App();
const stack = new Stack(app, "tesseract-ocr-example-cdk-py38");

const environment = {
  LOG_LEVEL: "INFO",
  TEXTRACTOR_OCR: "textractor_ocr",
  TEXTRACTOR_SIMPLE: "textractor_simple",
};

const createLambdaFunction = (name: string, path: string) => {
  const lambdaFunction = new lambda.Function(stack, name, {
    runtime: lambda.Runtime.PYTHON_3_8,
    code: lambda.Code.fromAsset(path),
    handler: "main.handle",
    memorySize: 1024,
    environment,
    timeout: Duration.seconds(800),
  });

  return lambdaFunction;
};

const functionsPath = path.join(__dirname, "./../functions");
const ocrTextractorPath = path.join(functionsPath, "/ocr");

const lambdas = [
  { name: environment.TEXTRACTOR_OCR, path: ocrTextractorPath },
  {
    name: environment.TEXTRACTOR_SIMPLE,
    path: path.join(functionsPath, "/simple"),
  },
];

lambdas.forEach(({ name, path }) => {
  createLambdaFunction(name, path);
});
