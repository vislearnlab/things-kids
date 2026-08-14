declare global {
  namespace NodeJS {
    interface ProcessEnv {
      ENVIRONMENT: 'development' | 'production';
      BASE_PATH?: string;
      MONGO_URL: string;
      DATABASE: string;
      COLLECTION: string;
      CREDENTIALS_PATH?: string;
      PORT?: string;
    }
  }
}
export {};
