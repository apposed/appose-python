#!/bin/sh

# Usage examples:
#   bin/test.sh
#   bin/test.sh test_appose.py
#   bin/test.sh test_appose.py::test_groovy

set -e

dir=$(dirname "$0")
cd "$dir/.."

if [ ! -d target/dependency ]
then
  echo "==> Installing appose-java..."
  mkdir -p target
  echo '<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.apposed</groupId>
  <artifactId>appose-python</artifactId>
  <version>0-SNAPSHOT</version>
  <dependencies>
    <dependency>
      <groupId>org.apposed</groupId>
      <artifactId>appose</artifactId>
      <version>LATEST</version>
    </dependency>
  </dependencies>
  <repositories>
    <repository>
      <id>scijava.public</id>
      <url>https://maven.scijava.org/content/groups/public</url>
    </repository>
  </repositories>
</project>' > appose.pom
  mvn -f appose.pom dependency:copy-dependencies
  rm appose.pom
fi

if [ $# -gt 0 ]
then
  python -m pytest -p no:faulthandler $@
else
  python -m pytest -p no:faulthandler tests
fi
