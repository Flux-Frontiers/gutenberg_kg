// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The query embedder: bge-small-en-v1.5, converted to Core ML by
// `gutenkg export-embedder` and run on the Neural Engine.
//
// It has to be *this* model. The packs hold bge-small vectors, and a query
// embedded by anything else — Apple's NLContextualEmbedding included — lands in
// a different space and returns confident nonsense. `embedder.json` records
// which model built the packs so the app can refuse a mismatch rather than
// discover it in an answer.

import CoreML
import Foundation

/// What `embedder.json` says about the model beside it.
public struct EmbedderDescriptor: Codable, Sendable {
    public struct Tokenizer: Codable, Sendable {
        public let kind: String
        public let lowercase: Bool
        public let vocab: String
        public let unkID: Int32
        public let clsID: Int32
        public let sepID: Int32
        public let padID: Int32
        public let continuingPrefix: String

        enum CodingKeys: String, CodingKey {
            case kind, lowercase, vocab
            case unkID = "unk_id"
            case clsID = "cls_id"
            case sepID = "sep_id"
            case padID = "pad_id"
            case continuingPrefix = "continuing_prefix"
        }
    }

    public let model: String
    public let dim: Int
    public let maxLength: Int
    public let pooling: String
    public let normalized: Bool
    public let tokenizer: Tokenizer

    enum CodingKeys: String, CodingKey {
        case model, dim, pooling, normalized, tokenizer
        case maxLength = "max_length"
    }
}

/// Embeds a query on the device, in the packs' vector space.
public final class BGEEmbedder: @unchecked Sendable {

    public enum EmbedderError: Error, LocalizedError {
        case missingFile(String)
        case modelMismatch(expected: String, found: String)
        case unexpectedOutput

        public var errorDescription: String? {
            switch self {
            case .missingFile(let name):
                return "\(name) is missing — run `gutenkg export-embedder` and copy it in."
            case .modelMismatch(let expected, let found):
                return
                    "The corpus was built with \(expected) but the app carries \(found). Searching would return nonsense, so it is disabled."
            case .unexpectedOutput:
                return "The embedding model returned an unexpected output shape."
            }
        }
    }

    public let descriptor: EmbedderDescriptor
    private let model: MLModel
    private let tokenizer: WordPieceTokenizer

    /// Load the converted model, its vocabulary, and its descriptor.
    ///
    /// :param directory: The folder holding `BGEEmbedder.mlpackage`,
    ///     `vocab.txt` and `embedder.json`.
    /// :param requiredModel: The model id the packs were built with; a
    ///     mismatch throws rather than silently returning wrong vectors.
    /// :param configuration: Core ML compute-unit configuration.
    /// :throws: ``EmbedderError`` or any Core ML load error.
    public init(
        directory: URL,
        requiredModel: String?,
        configuration: MLModelConfiguration = MLModelConfiguration()
    ) throws {
        let descriptorURL = directory.appendingPathComponent("embedder.json")
        guard let data = try? Data(contentsOf: descriptorURL) else {
            throw EmbedderError.missingFile("embedder.json")
        }
        let descriptor = try JSONDecoder().decode(EmbedderDescriptor.self, from: data)

        if let requiredModel, requiredModel != descriptor.model {
            throw EmbedderError.modelMismatch(expected: requiredModel, found: descriptor.model)
        }

        let vocabURL = directory.appendingPathComponent(descriptor.tokenizer.vocab)
        guard FileManager.default.fileExists(atPath: vocabURL.path) else {
            throw EmbedderError.missingFile(descriptor.tokenizer.vocab)
        }

        let packageURL = directory.appendingPathComponent("BGEEmbedder.mlpackage")
        guard FileManager.default.fileExists(atPath: packageURL.path) else {
            throw EmbedderError.missingFile("BGEEmbedder.mlpackage")
        }
        // Compiling once per launch is the documented path for a model that
        // ships as data rather than as a bundle resource.
        let compiled = try MLModel.compileModel(at: packageURL)

        let model = try MLModel(contentsOf: compiled, configuration: configuration)
        let tokenizer = try WordPieceTokenizer(
            vocabularyAt: vocabURL,
            configuration: .init(
                lowercase: descriptor.tokenizer.lowercase,
                unknownID: descriptor.tokenizer.unkID,
                classificationID: descriptor.tokenizer.clsID,
                separatorID: descriptor.tokenizer.sepID,
                paddingID: descriptor.tokenizer.padID,
                continuingPrefix: descriptor.tokenizer.continuingPrefix))

        self.descriptor = descriptor
        self.model = model
        self.tokenizer = tokenizer
    }

    /// Embed one query.
    ///
    /// CLS pooling and L2 normalisation are baked into the traced graph, so the
    /// output is directly comparable with a packed vector and there is no
    /// pooling decision left in Swift to get wrong.
    ///
    /// :param text: Query text.
    /// :returns: A unit-length embedding of ``EmbedderDescriptor/dim`` floats.
    /// :throws: ``EmbedderError/unexpectedOutput`` or a Core ML prediction error.
    public func embed(_ text: String) throws -> [Float] {
        let encoding = tokenizer.encode(text, maxLength: descriptor.maxLength)
        let shape: [NSNumber] = [1, NSNumber(value: descriptor.maxLength)]

        let ids = try MLMultiArray(shape: shape, dataType: .int32)
        let mask = try MLMultiArray(shape: shape, dataType: .int32)
        for (index, value) in encoding.inputIDs.enumerated() {
            ids[index] = NSNumber(value: value)
            mask[index] = NSNumber(value: encoding.attentionMask[index])
        }

        let input = try MLDictionaryFeatureProvider(dictionary: [
            "input_ids": MLFeatureValue(multiArray: ids),
            "attention_mask": MLFeatureValue(multiArray: mask),
        ])
        let output = try model.prediction(from: input)
        guard let array = output.featureValue(for: "embedding")?.multiArrayValue,
            array.count == descriptor.dim
        else { throw EmbedderError.unexpectedOutput }

        var vector = [Float](repeating: 0, count: descriptor.dim)
        for index in 0..<descriptor.dim {
            vector[index] = array[index].floatValue
        }
        return vector
    }
}
