import Foundation
import ImageIO
import Vision

struct Observation: Encodable {
    let text: String
    let x: CGFloat
    let y: CGFloat
    let width: CGFloat
    let height: CGFloat
}

struct Result: Encodable {
    let width: Int
    let height: Int
    let observations: [Observation]
}

guard CommandLine.arguments.count == 2 else {
    fputs("usage: vision-ocr <image>\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
      let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
      let width = properties[kCGImagePropertyPixelWidth] as? Int,
      let height = properties[kCGImagePropertyPixelHeight] as? Int else {
    fputs("unable to read image dimensions\n", stderr)
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "en-US"]

let handler = VNImageRequestHandler(url: imageURL, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("ocr failed: \(error)\n", stderr)
    exit(4)
}

let observations = (request.results as? [VNRecognizedTextObservation] ?? []).compactMap { item -> Observation? in
    guard let candidate = item.topCandidates(1).first else { return nil }
    let box = item.boundingBox
    return Observation(
        text: candidate.string,
        x: box.origin.x,
        y: 1 - box.origin.y - box.height,
        width: box.width,
        height: box.height
    )
}

do {
    let output = try JSONEncoder().encode(Result(width: width, height: height, observations: observations))
    FileHandle.standardOutput.write(output)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    fputs("json failed: \(error)\n", stderr)
    exit(5)
}
